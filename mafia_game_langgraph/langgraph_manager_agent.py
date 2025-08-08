import logging
import random
import json
import asyncio

from math import floor
from typing import Dict
from typing import TypedDict
from typing import Optional
from typing import Callable
from collections import Counter

from base_agent import BaseAgent
from a2a_core.server_executor import GenericAgentExecutor
from messages import Role
from messages import (
    Role,
    MessageType,
    create_message
    )
from dataclasses import dataclass

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
#from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


@dataclass
class AgentStatus:
    role: Role
    alive: bool = True

# 단계별 상태 저장을 위한 구조 정의
class GameState(TypedDict):
    agent_info: Dict[str, AgentStatus]
    round: int 
    game_over: int
    winner: str


logger = logging.getLogger(__name__)

class LangGraphManagerAgent(BaseAgent):
    """Manager Agent."""
    def __init__(self, agent_name: str, description: str):
        
        super().__init__(
            agent_name=agent_name,
            description=description,
            content_types=['text', 'text/plain'],
        )

        self.name = agent_name
        self.agent_info: Dict[str, AgentStatus] = {}
        self.executor: GenericAgentExecutor | None = None

        self.graph = StateGraph(GameState)
        self.setup_graph()
    
    def setup_graph(self):
         # 노드 정의
        self.graph.add_node("assign_roles", self.node_assign_roles)
        self.graph.add_node("day_phase", self.node_day_phase)
        self.graph.add_node("vote_phase", self.node_vote_phase)
        self.graph.add_node("night_phase", self.node_night_phase)
        self.graph.add_node("check_end", self.node_check_end)
        self.graph.set_entry_point("assign_roles")

        # 흐름 설정
        self.graph.add_edge("assign_roles", "day_phase")
        self.graph.add_edge("day_phase", "vote_phase")
        self.graph.add_edge("vote_phase", "night_phase")
        self.graph.add_edge("night_phase", "check_end")
        #self.graph.add_edge("day_phase", "check_end")

        # 반복 조건 + 종료 조건
        def next_phase(state: GameState):
            return END if state.get("game_over") else "day_phase"        
        self.graph.add_conditional_edges("check_end", next_phase)

        self.runnable = self.graph.compile(checkpointer=MemorySaver())
    
    
    def initialize(self, agent_names: list[str], executor: GenericAgentExecutor = None):
        self.executor = executor
        self.agent_list = agent_names


    def set_server_shutdown_callback(self, callback: Callable[[], None]):
        self.shutdown_callback = callback


    async def start_game(self, initial_state:dict):
        print("✅ LangGraph: 게임 시작")
        result_state = await self.runnable.ainvoke(initial_state,
            config={
                "configurable": {
                    "thread_id": "game-001",
                    "checkpoint_id": "mafia-001",
                    "checkpoint_ns": "mafia-namespace"
                }
            }
        )

        print("✅ 게임 종료. 최종 상태:", result_state)
        # 게임 종료 후 서버 종료
        if hasattr(self, "shutdown_callback"):
            self.shutdown_callback()
    

    async def node_assign_roles(self, state: GameState):
        """게임내 역할을 무작위로 할당합니다."""
        agent_names = self.agent_list
        total_agents = len(agent_names)
        if total_agents < 3:
            raise ValueError("플레이어 수가 3명 이상이어야 역할을 배정할 수 있습니다.")

        # 셔플
        random.shuffle(agent_names)

        # mafia 수 = 총 인원의 1/3, 최소 1명
        num_mafia = max(1, total_agents // 3)
        num_detective = 1
        for i, nm in enumerate(agent_names):
            if i < num_mafia:
                role = Role.MAFIA
            elif i < num_mafia + num_detective:
                role = Role.DETECTIVE
            else:
                role = Role.VILLAGER

            state["agent_info"][nm] = AgentStatus(role=role, alive=True)

        print("역할이 무작위로 할당되었습니다:")
        for agent_name, status in state["agent_info"].items():
            print(f"  - {agent_name}: {status.role.name} (alive={status.alive})")
        
        for agent_name, status in state["agent_info"].items():
            try:
                msg = create_message(MessageType.ROLE_ASSIGNMENT, self.name, agent_name, role=status.role)
                asyncio.create_task(await self.executor.send_to_other(agent_name, msg))
                print(f"역할 전송 완료: {agent_name} → {status.role.name}")
            except Exception as e:
                print(f"역할 전송 실패: {agent_name} → {status.role.name} ({e})")

        return state


    async def node_day_phase(self, state: GameState):
        round = state["round"]
        print(f"{round} 낮 시작 메시지를 모든 에이전트에게 전송합니다.")

        if round <= 1 : 
            
            for nm, status in state["agent_info"].items():
                if status.alive:
                    msg = create_message(MessageType.INTRO_REQUEST, self.name, nm, round=round)
                    asyncio.create_task(self.executor.send_to_other(nm, msg))

        else : 
            print("💬 토론 시간이 주어집니다. 멤버들이 자유롭게 대화할 수 있습니다.")

            for nm, status in state["agent_info"].items():
                if status.alive:
                    msg = create_message(MessageType.DAY_ACTION_REQUEST, self.name, nm, round=round)
                    asyncio.create_task(self.executor.send_to_other(nm, msg))
            

            # 비동기로 잠시 대기 (예: 15초)
            await asyncio.sleep(15)

            print("🕒 토론 시간이 종료되었습니다.")

        state["round"] = round+1
        return state


    async def node_vote_phase(self, state: GameState) -> GameState:
        # 1. Vote 
        votes: Dict[str, str] = {}
        agent_info = state["agent_info"]
        alive_agents = [name for name, status in agent_info.items() if status.alive]

        async def send_and_receive_vote(agent_name: str):
            msg = create_message(MessageType.VOTE_REQUEST, self.name, agent_name, round=state["round"])
            try:
                response = await asyncio.wait_for(self.executor.send_to_other(agent_name, msg), timeout=10)
                if response:
                    print(f"🗳️ {agent_name} → {response[0]}")
                    return (agent_name, response[0])
                else:
                    print(f"⚠️ {agent_name} 응답 없음.")
                    return (agent_name, None)
            except Exception as e:
                print(f"❌ {agent_name} 응답 실패: {e}")
                return (agent_name, None)

        # 모든 요청을 병렬 실행
        results = await asyncio.gather(*(send_and_receive_vote(name) for name in alive_agents))

        # 결과 정리
        votes: Dict[str, str] = {
            voter: vote for voter, vote in results if vote is not None
        }

        # 투표 집계 후 상태에 반영
        state["last_votes"] = votes

        # 2. 처형될 후보자 선택 
        target = None
        counter = Counter(votes.values())
        if counter : 
            max_votes = max(counter.values())
            candidates = [name for name, count in counter.items() if count == max_votes]

            if len(candidates) == 1 : 
                target = candidates[0]  # 단일 최다 득표자
            else :
                target = random.choice(candidates)  # 동률 시 랜덤 선택
        
        if target and target in agent_info : 
            state["agent_info"][target].alive = False
            print(f"🔪 {target} 가 처형되었습니다.")
            for agent_name in agent_info.keys():
                msg = create_message(MessageType.EXECUTION_RESULT, self.name, agent_name, target=target)
                await self.executor.send_to_other(agent_name, msg)

        else : 
            print("⚖️ 처형 없음 (동률 또는 투표 실패).")

        return state


    async def node_night_phase(self, state: GameState):
        
        print("\n🌙 밤이 되었습니다. 마피아는 공격할 대상을 선택하고, 경찰은 조사를 수행합니다.\n")
        agent_info = state["agent_info"]
        
        mafia_targets = []
        detective_results = {}
       
        for agent_name, status in agent_info.items():
            if not status.alive:
                continue

            # 4-1. 마피아의 밤 공격
            if status.role == Role.MAFIA:
                try:
                    message = create_message(MessageType.NIGHT_ACTION_REQUEST, self.name, agent_name, role=status.role)
                    response = await self.executor.send_to_other(agent_name, message)
                    if response:
                        mafia_targets.append(response[0])
                        print(f"🧟‍♂️ {agent_name} → {response[0]}")
                except Exception as e:
                    print(f"❌ 마피아 행동 실패: {e}")

            # 4-2. 경찰의 조사
            elif status.role == Role.DETECTIVE:
                try:
                    message = create_message(MessageType.NIGHT_ACTION_REQUEST, self.name, agent_name, role=status.role)
                    response = await self.executor.send_to_other(agent_name, message)
                    if response:
                        target = response[0]
                        is_mafia = agent_info.get(target, AgentStatus(Role.VILLAGER)).role == Role.MAFIA
                        detective_results[agent_name] = (target, is_mafia)
                        print(f"🕵️ {agent_name} → {target} is {'MAFIA' if is_mafia else 'NOT MAFIA'}")
                except Exception as e:
                    print(f"❌ 경찰 행동 실패: {e}")

        # 4-3. 마피아 타겟 결정 (복수일 경우 랜덤 선택)
        if mafia_targets:
            votes = Counter(mafia_targets)
            max_vote = max(votes.values())
            candidates = [name for name, count in votes.items() if count == max_vote]
            killed = random.choice(candidates)
            if killed in agent_info:
                state["agent_info"][killed].alive = False
                print(f"\n💀 밤 동안 {killed} 가 제거되었습니다.")

                # 전체에게 제거 사실을 알림
                for agent_name in agent_info.keys():
                    msg = create_message(MessageType.KILLED_RESULT, self.name, agent_name, target=killed)
                    await self.executor.send_to_other(agent_name, msg)
        else:
            print("😴 마피아가 아무도 제거하지 않았습니다.")

        # 4-4. 경찰에게 조사 결과 전달
        for detective, (target, is_mafia) in detective_results.items():
            try:
                message = create_message(MessageType.NIGHT_ACTION_RESULT, self.name, detective, target=target, is_mafia=is_mafia)
                await self.executor.send_to_other(detective, message)
            except Exception as e:
                print(f"❌ 경찰 결과 전송 실패: {e}")

        return state

    async def node_check_end(self, state: GameState):
        over, winner = self.evaluate_game_over(state["agent_info"])
        state["game_over"] = over

        if over : 
            print(f"🏁 게임 종료! 승리 팀: {winner}")

            state["winner"] = winner
            for agent_name in state["agent_info"].keys():
                msg = create_message(MessageType.GAME_RESULT, self.name, agent_name, winner=winner)
                await self.executor.send_to_other(agent_name, msg)
                     
        return state

    def evaluate_game_over(self, agent_info: Dict[str, AgentStatus]):
        """
        게임 종료 조건을 확인합니다.
        Returns:
            (is_over: bool, winner: Optional[str])
        """
        mafia_count = sum(1 for s in agent_info.values() if s.alive and s.role == Role.MAFIA)
        others_count = sum(1 for s in agent_info.values() if s.alive and s.role != Role.MAFIA)

        if mafia_count == 0:
            return True, "CITIZENS"
        elif mafia_count >= others_count:
            return True, "MAFIA"
        else:
            return False, None

        


        