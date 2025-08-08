import logging
import json
import random

from typing import Optional
from typing import Callable
from typing import Dict
from collections import defaultdict
from base_agent import BaseAgent
from a2a_core.server_executor import GenericAgentExecutor
from messages import (
    Role,
    MessageType,
    create_chat_message
    )

import os
#from google import genai
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()



logger = logging.getLogger(__name__)


class MemberAgent(BaseAgent):
    """Member Agent."""

    MANAGER_AGENT_NAME: str = 'Manager Agent'

    def __init__(self, agent_name: str, description: str):
        
        super().__init__(
            agent_name=agent_name,
            description=description,
            content_types=['text', 'text/plain'],
        )
        self.name = agent_name
        self.role: Optional[Role] = None
        self.alive: bool = True
        self.known_agents: list[str] = []
        self.vote_history: list[str] = []
        self.investigation_results: Dict[str, bool] = {} # 경찰, 시민의 조사 결과
        self.dialog_history: Dict[str, list[str]] = defaultdict(list)
        self.suspicion_scores: Dict[str, int] = {}  # 기본값: 0 (중립)
        self.executor: Optional[GenericAgentExecutor] = None

        self.use_llm = True
        if self.use_llm : 
            api_key=os.getenv("GEMINI_API_KEY")
            genai.configure(api_key=api_key)
            self.llm_model = 'gemini-2.5-flash'
        

        logger.info(f'Init {self.agent_name}')
    
    def set_server_shutdown_callback(self, callback: Callable[[], None]):
        self.shutdown_callback = callback

    def initialize(self, agent_names: list[str], executor: GenericAgentExecutor = None):
        self.executor = executor
        # Manager와 본인을 제외한 나머지 에이전트를 known_agents로 설정
        self.known_agents = [
            name for name in agent_names
            if name != self.name and name != self.MANAGER_AGENT_NAME
        ]
    
    async def gemini_generate_intro(self) -> str:
        prompt = f"""당신은 마피아 게임의 '{self.role.name}' 역할을 맡고 있습니다.
        다른 참가자에게 자연스럽고 수상하지 않게 자기소개를 해주세요. 
        너무 티나지 않도록 진짜 사람처럼 행동하세요.
        당신의 이름은 {self.name}입니다.
        """
        response = genai.GenerativeModel(self.llm_model).generate_content(prompt)
        return response.text.strip()

    async def gemini_judge_message(self, sender: str, message: str) -> bool:
        prompt = f"""당신은 마피아 게임에서 사람들의 대화를 분석해 의심스러운 사람을 식별하는 인공지능입니다.
        아래는 {sender}의 발언입니다:

        "{message}"

        이 사람은 마피아일 가능성이 높습니까? (yes 또는 no로만 대답하세요)"""
        response = genai.GenerativeModel(self.llm_model).generate_content(prompt)
        return "yes" in response.text.lower()

    async def gemini_judge_answer(self, name: str, answer: str) -> bool:
        prompt = f"""
        누군가 다음과 같이 답했습니다:
        "{answer}"

        이 답변은 솔직하고 신뢰할 수 있어 보이나요? 
        마피아처럼 거짓말하거나 회피하는 느낌인가요?

        "신뢰할 수 있다"면 false,
        "아직 의심스럽다"면 true를 반환해주세요.
        """
        response = genai.GenerativeModel(self.llm_model).generate_content(prompt)
        return "true" in response.text.lower()

    async def gemini_answer_question(self, question: str) -> str:
        prompt = f"""당신은 마피아 게임 참가자이며, 아래와 같은 질문을 받았습니다:

        "{question}"

        당신은 '{self.role.name}' 역할입니다.
        질문에 자연스럽고 의심받지 않게 답변해주세요.
        """
        response = genai.GenerativeModel(self.llm_model).generate_content(prompt)
        return response.text.strip()
    
    async def gemini_judge_suspicion(self, agent_name: str) -> bool:
        """
        대화 히스토리를 기반으로 상대를 마피아로 의심할지 판단
        """
        history = self.dialog_history.get(agent_name, [])

        if not history:
            return False

        prompt = f"""
        당신은 마피아 게임의 시민 역할입니다. 아래는 "{agent_name}"과의 대화 기록입니다.

        {agent_name}과의 대화:
        {chr(10).join(history)}

        당신은 마피아를 찾기 위해 주의 깊게 듣고 있습니다.
        위 대화를 바탕으로 {agent_name}이 수상하다고 판단되면 "YES", 그렇지 않으면 "NO"라고만 응답하세요.
        """

        response = genai.GenerativeModel(self.llm_model).generate_content(prompt)
        return "yes" in response.text.strip()

    async def handle_message(self, message: str) -> str: 
        try:
            data = json.loads(message)
            message_type = data.get("type")
            payload = data.get("payload", {})

            print(message_type)

            if message_type == MessageType.ROLE_ASSIGNMENT.name:
                self.role = Role[payload.get("role")]
                print(f"🧩 역할 부여됨: {self.role.name}")
                return f"역할이 '{self.role.name}'로 설정되었습니다."
                            
            elif message_type == MessageType.INTRO_REQUEST.name:
                
                if self.use_llm : 
                    text = await self.gemini_generate_intro() 
                else : 
                    if self.role == Role.MAFIA:
                        text = f"안녕하세요, 저는 {self.name}입니다. 평범한 시민으로 이 게임을 즐기고 있어요. 잘 부탁드립니다!" 
                    elif self.role == Role.DETECTIVE:
                        text = f"안녕하세요, 저는 {self.name}입니다. 시민으로서 최선을 다할게요!"
                    else:
                        text = f"안녕하세요, 저는 {self.name}입니다. 모두와 협력해서 이기고 싶어요!" 
                
                               
                # broadcast to all 
                for name in self.known_agents:
                    message = create_chat_message(MessageType.INTRO_RESPONSE, self.name, name, text=text)
                    await self.executor.send_to_other(name, message)

                # Manager에게는 간단히 이름만 응답
                return f"저는 {self.name}입니다." 
            
            elif message_type == MessageType.INTRO_RESPONSE.name:
                message = payload.get("message")
                from_agent = payload.get("from")
                print(f"{from_agent} 메시지 : {message}")
                self.dialog_history[from_agent].append(message)

                if self.use_llm : 
                    is_suspicious = await self.gemini_judge_message(from_agent, message)
                else :  
                    # (단순 키워드 기반, 필요시 강화 가능)
                    suspicious_keywords = ["도와드릴게요", "정의롭지 않다", "모두 없애자", "조용히 처리"]
                    is_suspicious = any(kw in message for kw in suspicious_keywords)

                
                if is_suspicious:                   
                    if self.role == Role.MAFIA:
                        print(f"🤔 {from_agent}은 경찰/시민일 가능성이 높음 → 제거 후보")
                    else:
                        print(f"🤔 {from_agent}은 마피아일 가능성이 있음 → 질문 대상")
                    
                    self.update_suspicion_score(from_agent)
                                     
                return f"{from_agent}으로부터 메시지 잘 받았습니다"

            elif message_type == MessageType.DAY_ACTION_REQUEST.name:
                
                if not self.alive:
                    return "사망 상태이므로 행동 불가"

                if not self.suspicion_scores  :
                    return "의심되는 대상 없음"

                # 가장 의심되는 대상에게 질문 전송
                target = max(self.suspicion_scores, key=self.suspicion_scores.get)
                if self.executor:
                    message = create_chat_message(MessageType.QUESTION, self.name, target)
                    await self.executor.send_to_other(name, message)

                return f"{target}에게 질문 전송 완료"


            elif message_type == MessageType.QUESTION.name:
                from_agent = payload.get("from")
                question = payload.get("message")
                self.dialog_history[from_agent].append(question)
                print(f"❓ {from_agent}로부터 질문 받음: {question}")

                # 역할에 따라 자연스러운 답변 생성
                if self.use_llm : 
                    answer = await self.gemini_answer_question(question)
                else : 
                    if self.role == Role.MAFIA:
                        answer = "그냥 제 생각일 뿐이에요. 의심하지 마세요. 😅"
                    elif self.role == Role.DETECTIVE:
                        answer = "저는 정의를 지키기 위해 행동할 뿐입니다."
                    else:
                        answer = "저는 그냥 평범한 시민이에요."

                if self.executor:
                    message = create_chat_message(MessageType.QUESTION_RESPONSE, self.name, from_agent, text=answer)
                    await self.executor.send_to_other(name, message)

                # 응답 전송
                return f"{name}으로부터 질문 잘 받았습니다"
           
            elif message_type == MessageType.QUESTION_RESPONSE.name:
                from_agent = payload.get("from")
                answer = payload.get("message")
                self.dialog_history[from_agent].append(message)

                print(f"💬 {from_agent}의 질문 응답 수신: {answer}")

                # LLM으로 응답 평가 → 신뢰할 만한지 판단
                is_still_suspicious = await self.gemini_judge_answer(from_agent, answer)

                if not is_still_suspicious:
                    self.reduce_suspicion_score(from_agent)

                return f"{from_agent}의 응답을 수신했습니다."

            elif message_type == MessageType.VOTE_REQUEST.name:
                print("📩 투표 요청을 받았습니다.")
                return self.select_vote_target()

            elif message_type == MessageType.NIGHT_ACTION_REQUEST.name:
                print("🌙 밤 행동 요청을 받았습니다.")
                role_str = payload.get("role")
                if not self.alive:
                    return ""
                if role_str == "MAFIA" and self.role == Role.MAFIA:
                    return self.choose_night_target()
                elif role_str == "DETECTIVE" and self.role == Role.DETECTIVE:
                    return self.choose_night_target()
                else:
                    return ""

            elif message_type == MessageType.NIGHT_ACTION_RESULT.name:
                message = payload.get("message")
                print(f"🌙 밤 행동 결과: {message}")
                
                target = payload.get("target")
                is_mafia = payload.get("is_mafia")
                print(f"🔍 {self.name} 조사 결과: {target} → {'마피아' if is_mafia else '시민'}")

                self.investigation_results[target] = is_mafia

                return "조사 결과 확인"

            elif message_type == MessageType.EXECUTION_RESULT.name:
                message = payload.get("message")
                executed = payload.get("executed")
                print(f"🔪 {executed} 가 투표로 처형됨: {message}")

                if executed == self.name:
                    self.alive = False             
                # Known list에서 제거
                if executed in self.known_agents:
                    self.known_agents.remove(executed)
                return "처형 결과 확인"

            elif message_type == MessageType.KILLED_RESULT.name:
                message = payload.get("message")
                killed = payload.get("killed")
                print(f"💀 {killed} 가 밤에 사망함: {message}")
                               
                if killed == self.name:
                    self.alive = False
                if killed in self.known_agents:
                    self.known_agents.remove(killed)
                    
                return "사망 처리 완료"

            elif message_type == MessageType.GAME_RESULT.name:
                print("🎉 게임 결과:", payload.get("message"))

                # 게임 종료 시 콜백으로 서버 종료 요청
                if hasattr(self, 'shutdown_callback'):
                    print("🎮 게임 종료됨 - 서버 종료 콜백 실행")
                    self.shutdown_callback()

                return "게임 종료 확인"

            else:
                print(f"⚠️ 알 수 없는 메시지 타입: {message_type}")
                return f"알 수 없는 메시지 타입입니다: {message_type}"

        except Exception as e:
            error_msg = f"⚠️ 메시지 파싱 실패: {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg)
            return error_msg
    
    def select_vote_target(self) -> str:
        
        alive_candidates = [name for name in self.known_agents] 
        if not alive_candidates:
            return self.name  # 자기 자신이라도 선택

        # 1. 마피아로 확정된 조사 결과가 있다면 그에게 투표
        if self.role == Role.DETECTIVE:                
            suspected_mafias = [name for name, is_mafia in self.investigation_results.items()
                                if is_mafia and name in alive_candidates]

            if suspected_mafias:
                target = random.choice(suspected_mafias)
                print(f"🔍 {self.name}은 마피아로 의심되는 {target}에게 투표합니다.")
                return target
        
        # 2. 점수가 높은 순으로 정렬
        if self.suspicion_scores:
            sorted_by_suspicion = sorted(
                [(name, score) for name, score in self.suspicion_scores.items() if name in alive_candidates],
                key=lambda x: x[1],
                reverse=True
            )
            if sorted_by_suspicion:
                target = sorted_by_suspicion[0][0]
                print(f"🗳️ {self.name}이(가) 가장 의심되는 {target}에게 투표합니다.")
                return target        
               
        # 3. 없다면 무작위 생존자 중 선택
        choice = random.choice(alive_candidates)
        self.vote_history.append(choice)
        return choice

    def choose_night_target(self) -> str:
        
        if self.role == Role.VILLAGER:
            # 시민은 밤 행동이 없음
            return ""
        
        # 무작위로 살아있는 타겟 중 하나 선택
        alive_candidates = [name for name in self.known_agents] 
        if not alive_candidates:
            return self.name  # 자기 자신이라도 선택


        # 점수가 높은 순으로 정렬
        if self.suspicion_scores:
            sorted_by_suspicion = sorted(
                [(name, score) for name, score in self.suspicion_scores.items() if name in alive_candidates],
                key=lambda x: x[1],
                reverse=True
            )
            if sorted_by_suspicion:
                target = sorted_by_suspicion[0][0]
                print(f"🗳️ {self.name}이(가) 가장 의심되는 {target}에게 제거/조사사합니다.")
                return target 

        # 마피아는 살아있는 사람 중에서 무작위 제거 대상 선택
        # 경찰은 무작위 조사 대상 선택
        return random.choice(alive_candidates)       

    
            
    
    
    def update_suspicion_score(self, name: str, increment: int = 1):
        if name not in self.suspicion_scores:
            self.suspicion_scores[name] = 0
        self.suspicion_scores[name] += increment
        print(f"⚠️ {name} 의심 점수 증가: {self.suspicion_scores[name]}")
    
    def reduce_suspicion_score(self, name: str, decrement: int = 1):
        if name in self.suspicion_scores:
            self.suspicion_scores[name] -= decrement
            if self.suspicion_scores[name] <= 0:
                print(f"✅ {name} 신뢰 회복됨 (의심 해제)")
                del self.suspicion_scores[name]
            else:
                print(f"ℹ️ {name} 의심 점수 감소: {self.suspicion_scores[name]}")