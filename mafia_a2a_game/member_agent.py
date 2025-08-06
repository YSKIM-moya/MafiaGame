import logging
import json
import random

from typing import Optional
from typing import Callable
from base_agent import BaseAgent
from a2a_core.server_executor import GenericAgentExecutor
from messages import (
    Role,
    MessageType
    )


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
        self.investigation_results: Dict[str, bool] = {} # 경찰, 시민의 조사 결과과
        self.suspicious_targets: list[str] = []  # 마피아가 의심하는 시민 목록
        self.executor: Optional[GenericAgentExecutor] = None

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

    async def handle_message(self, message: str) -> str: 
        try:
            data = json.loads(message)
            message_type = data.get("type")
            payload = data.get("payload", {})

            if message_type == MessageType.ROLE_ASSIGNMENT.name:
                self.role = Role[payload.get("role")]
                print(f"🧩 역할 부여됨: {self.role.name}")
                return f"역할이 '{self.role.name}'로 설정되었습니다."
                            
            elif message_type == MessageType.INTRO_REQUEST.name:
                
                if self.role == Role.MAFIA:
                    text = f"안녕하세요, 저는 {self.name}입니다. 평범한 시민으로 이 게임을 즐기고 있어요. 잘 부탁드립니다!" 
                elif self.role == Role.DETECTIVE:
                    text = f"안녕하세요, 저는 {self.name}입니다. 시민으로서 최선을 다할게요!"
                else:
                    text = f"안녕하세요, 저는 {self.name}입니다. 모두와 협력해서 이기고 싶어요!" 

                # broadcast to all 
                for name in self.known_agents:
                    request_message = {
                        "type": MessageType.INTRO_RESPONSE.name,
                        "payload": {
                            "message": text,
                            "name" : self.name
                        }
                    }
                    await self.executor.send_to_other(name, json.dumps(request_message))

                # Manager에게는 간단히 이름만 응답
                return f"안녕하세요, 저는 {self.name}입니다." 
            
            elif message_type == MessageType.INTRO_RESPONSE.name:
                message = payload.get("message")
                name = payload.get("name")
                print(f"{name} 메시지 : {message}")

                # TODO : 판단, 의심 
                # ✅ 1. 의심 기준 예시 (단순 키워드 기반, 필요시 강화 가능)
                suspicious_keywords = ["도와드릴게요", "정의롭지 않다", "모두 없애자", "조용히 처리"]
                is_suspicious = any(kw in message for kw in suspicious_keywords)

                if is_suspicious:
                    print(f"⚠️ {name}이(가) 수상합니다. 질문을 보냅니다.")
                    self.update_suspicion(name)

                    # ✅ 2. 질문 메시지 전송
                    if self.executor:
                        question_message = {
                            "type": MessageType.QUESTION.name,
                            "payload": {
                                "from": self.name,
                                "to": name,
                                "question": f"{name}, 그렇게 말한 이유가 뭔가요?"
                            }
                        }
                        await self.executor.send_to_other(name, json.dumps(question_message))

                return f"{name}으로부터 메시지 수신 확인"


            elif message_type == MessageType.QUESTION.name:
                from_agent = payload.get("from")
                question = payload.get("question")

                print(f"❓ {from_agent}로부터 질문 받음: {question}")

                # 역할에 따라 자연스러운 답변 생성
                if self.role == Role.MAFIA:
                    answer = "그냥 제 생각일 뿐이에요. 의심하지 마세요. 😅"
                elif self.role == Role.DETECTIVE:
                    answer = "저는 정의를 지키기 위해 행동할 뿐입니다."
                else:
                    answer = "저는 그냥 평범한 시민이에요."

                # 응답 전송
                return answer

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

        if self.role == Role.MAFIA:        
            possible_targets = [n for n in self.suspicious_targets if n in alive_candidates]
            if possible_targets:
                target = random.choice(possible_targets)
                print(f"😈 {self.name} (마피아)은 의심 대상을 투표합니다: {target}")
                return target
        else: 
            # 1. 마피아로 확정된 조사 결과가 있다면 그에게 투표
            suspected_mafias = [name for name, is_mafia in self.investigation_results.items()
                                if is_mafia and name in alive_candidates]

            if suspected_mafias:
                target = random.choice(suspected_mafias)
                print(f"🔍 {self.name}은 마피아로 의심되는 {target}에게 투표합니다.")
                return target
        
                
               
        # 2. 없다면 무작위 생존자 중 선택
        choice = random.choice(alive_candidates)
        self.vote_history.append(choice)
        return choice

    def choose_night_target(self) -> str:
        # 무작위로 살아있는 타겟 중 하나 선택
        alive_candidates = [name for name in self.known_agents] 
        if not alive_candidates:
            return self.name  # 자기 자신이라도 선택

        if self.role == Role.MAFIA:
            # 마피아는 살아있는 사람 중에서 무작위 제거 대상 선택
            return random.choice(alive_candidates)

        elif self.role == Role.DETECTIVE:
            # 경찰은 무작위 조사 대상 선택
            return random.choice(alive_candidates)

        else:
            # 시민은 밤 행동이 없음
            return ""
    
    def update_suspicion(self, target: str):
        if target not in self.suspicious_targets:
            self.suspicious_targets.append(target)