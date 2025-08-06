
import logging
import random
import json
import asyncio

from math import floor
from typing import Dict
from typing import Optional
from typing import Callable
from collections import Counter

from base_agent import BaseAgent
from a2a_core.server_executor import GenericAgentExecutor
from messages import Role
from messages import (
    Role,
    MessageType,
    create_role_assignment_message
    )
from dataclasses import dataclass

@dataclass
class AgentStatus:
    role: Role
    alive: bool = True

logger = logging.getLogger(__name__)



class ManagerAgent(BaseAgent):
    """Manager Agent."""

    def __init__(self):
        
        super().__init__(
            agent_name='Manager Agent',
            description='Facilitate inter agent communication',
            content_types=['text', 'text/plain'],
        )

        self.agent_info: Dict[str, AgentStatus] = {}
        self.executor: GenericAgentExecutor | None = None

    def set_server_shutdown_callback(self, callback: Callable[[], None]):
        self.shutdown_callback = callback


    def initialize(self, agent_names: list[str], executor: GenericAgentExecutor = None):
        self.executor = executor
        self.assign_roles(agent_names)
        #await self.run_game_loop()


    # 1. Role 할당
    def assign_roles(self, agent_names: list[str]):
        """게임내 역할을 무작위로 할당합니다."""
        total_agents = len(agent_names)
        if total_agents < 3:
            raise ValueError("플레이어 수가 3명 이상이어야 역할을 배정할 수 있습니다.")
        
        # 셔플
        random.shuffle(agent_names)

        # mafia 수 = 총 인원의 1/3, 최소 1명
        num_mafia = max(1, floor(total_agents / 3))
        num_detective = 1
        num_villager = total_agents - num_mafia - num_detective

        # 역할 할당
        self.agent_info: Dict[str, AgentStatus] = {}

        for i, name in enumerate(agent_names):
            if i < num_mafia:
                role = Role.MAFIA
            elif i < num_mafia + num_detective:
                role = Role.DETECTIVE
            else:
                role = Role.VILLAGER

            self.agent_info[name] = AgentStatus(role=role, alive=True)

        print("✅ 역할이 무작위로 할당되었습니다:")
        for name, status in self.agent_info.items():
            print(f"  - {name}: {status.role.name} (alive={status.alive})")


    # Game Loop
    async def run_game_loop(self):
        if not self.executor:
            print("❌ Executor가 설정되어 있지 않습니다.")
            return

        print("🎲 게임을 시작합니다...\n")

        # 1. 역할 할당 및 통보
        await self.notify_roles_to_agents()

        round_num = 1
        while True:
            print(f"\n🌞 낮 {round_num} 시작")

            # 2. 낮 - 자기소개 요청
            await self.request_introduction()

            # 멤버들끼리 자유 대화 
            await asyncio.sleep(5)

            # 3. 낮 - 투표 및 처형
            await self.execute_vote_phase()

            # 4. 게임 종료 체크
            is_over, winner = self.is_game_over()
            if is_over:
                await self.announce_winner(winner)
                break

            print(f"\n🌙 밤 {round_num} 시작")
            
            # 5. 밤 - 마피아/경찰 행동
            await self.execute_night_phase()

            # 6. 게임 종료 체크
            is_over, winner = self.is_game_over()
            if is_over:
                await self.announce_winner(winner)
                break

            round_num += 1
        
        # 게임 종료 시 콜백으로 서버 종료 요청
        if hasattr(self, 'shutdown_callback'):
            print("🎮 게임 종료됨 - 서버 종료 콜백 실행")
            self.shutdown_callback()

    # 1. 역할 할당 및 통보
    async def notify_roles_to_agents(self):
        """모든 에이전트에게 자신의 역할을 비공개로 알립니다."""

        if not self.executor:
            print("❌ Executor가 설정되어 있지 않습니다.")
            return

        for agent_name, status in self.agent_info.items():
            try:
                message_dict = create_role_assignment_message(status.role)
                # JSON 문자열로 직렬화 
                message = json.dumps(message_dict)

                await self.executor.send_to_other(agent_name, message)
                print(f"✅ 역할 전송 완료: {agent_name} → {status.role.name}")
            except Exception as e:
                print(f"⚠️ 역할 전송 실패: {agent_name} → {status.role.name} ({e})")    

 

    # 2. 자기 소개 
    async def request_introduction(self):
        """모든 에이전트에게 낮 시작 자기소개 요청 메시지를 보냅니다."""
        
        message_dict = {
            "type": MessageType.INTRO_REQUEST.name,  
            "payload": {
                "message": "🌞 첫째날 낮이 되었습니다. 모두 자기소개를 해주세요."
            }
        }

        message = json.dumps(message_dict)

        await self.broadcast_to_roles(message)
        print("📢 낮 시작 메시지를 모든 에이전트에게 전송했습니다.")


    # 3. 낮 행동 : 투표 
    async def execute_vote_phase(self):
        votes = await self.request_votes()
        executed = self.count_votes(votes)

        if executed and executed in self.agent_info:
            self.agent_info[executed].alive = False
            print(f"🔪 {executed} 가 처형되었습니다.")

            result_msg = {
                "type": MessageType.EXECUTION_RESULT.name,
                "payload": {
                    "message": f"🔪 {executed} 가 투표로 처형되었습니다.",
                    "executed": executed
                }
            }

            await self.broadcast_to_roles(json.dumps(result_msg))

        else:
            print("⚖️ 처형 없음 (동률 또는 투표 실패).")

    async def request_votes(self) -> Dict[str, str]:
        """모든 살아있는 에이전트에게 투표 요청하고 응답 수집."""
       
        message_dict = {
            "type": MessageType.VOTE_REQUEST.name,
            "payload": {
                "message": "🗳️ 누구를 처형할지 투표해주세요. 살아있는 에이전트 이름 중에서 선택하세요."
            }
        }

        message = json.dumps(message_dict)

              
        # 응답 수집
        votes: Dict[str, str] = {}
        for agent_name, status in self.agent_info.items():
            if not status.alive:
                continue

            try:
                response_list = await self.executor.send_to_other(agent_name, message)
                if response_list:
                    vote_target = response_list[0]
                    votes[agent_name] = vote_target
                    print(f"🗳️ {agent_name} → {vote_target}")
                else:
                    print(f"⚠️ {agent_name} 응답 없음.")
            except Exception as e:
                print(f"❌ {agent_name} 응답 실패: {e}")

        return votes

    def count_votes( self, votes: Dict[str, str]) -> Optional[str]:
        

        counter = Counter(votes.values())
        if not counter:
            return None

        max_votes = max(counter.values())
        candidates = [name for name, count in counter.items() if count == max_votes]

        if len(candidates) == 1:
            return candidates[0]  # 단일 최다 득표자
        else:
            return random.choice(candidates)  # 동률 시 랜덤 선택


    # 4. 밤 행동
    async def execute_night_phase(self):
        print("\n🌙 밤이 되었습니다. 마피아는 공격할 대상을 선택하고, 경찰은 조사를 수행합니다.\n")

        mafia_targets = []
        detective_results = {}

        for name, status in self.agent_info.items():
            if not status.alive:
                continue

            # 4-1. 마피아의 밤 공격
            if status.role == Role.MAFIA:
                try:
                    message = json.dumps({
                        "type": MessageType.NIGHT_ACTION_REQUEST.name,
                        "payload": {
                            "role": "MAFIA",
                            "message": "밤입니다. 제거할 대상을 선택하세요."
                        }
                    })
                    response = await self.executor.send_to_other(name, message)
                    if response:
                        mafia_targets.append(response[0])
                        print(f"🧟‍♂️ {name} → {response[0]}")
                except Exception as e:
                    print(f"❌ 마피아 행동 실패: {e}")

            # 4-2. 경찰의 조사
            elif status.role == Role.DETECTIVE:
                try:
                    message = json.dumps({
                        "type": MessageType.NIGHT_ACTION_REQUEST.name,
                        "payload": {
                            "role": "DETECTIVE",
                            "message": "밤입니다. 조사할 대상을 선택하세요."
                        }
                    })
                    response = await self.executor.send_to_other(name, message)
                    if response:
                        target = response[0]
                        is_mafia = self.agent_info.get(target, AgentStatus(Role.VILLAGER)).role == Role.MAFIA
                        detective_results[name] = (target, is_mafia)
                        print(f"🕵️ {name} → {target} is {'MAFIA' if is_mafia else 'NOT MAFIA'}")
                except Exception as e:
                    print(f"❌ 경찰 행동 실패: {e}")

        # 4-3. 마피아 타겟 결정 (복수일 경우 랜덤 선택)
        if mafia_targets:
            votes = Counter(mafia_targets)
            max_vote = max(votes.values())
            candidates = [name for name, count in votes.items() if count == max_vote]
            killed = random.choice(candidates)
            if killed in self.agent_info:
                self.agent_info[killed].alive = False
                print(f"\n💀 밤 동안 {killed} 가 제거되었습니다.")

                # 전체에게 제거 사실을 알림
                result_message = {
                    "type": MessageType.KILLED_RESULT.name,
                    "payload": {
                        "message": f"💀 밤 사이 {killed} 가 사망했습니다.",
                        "killed": killed
                    }
                }
                await self.broadcast_to_roles(json.dumps(result_message))
        else:
            print("😴 마피아가 아무도 제거하지 않았습니다.")

        # 4-4. 경찰에게 조사 결과 전달
        for detective, (target, is_mafia) in detective_results.items():
            try:
                result_message = {
                    "type": MessageType.NIGHT_ACTION_RESULT.name,
                    "payload": {
                        "message": f"🔍 당신이 조사한 {target} 은(는) {'마피아' if is_mafia else '시민'}입니다.",
                        "target": target,
                        "is_mafia": is_mafia
                    }
                }
                await self.executor.send_to_other(detective, json.dumps(result_message))
            except Exception as e:
                print(f"❌ 경찰 결과 전송 실패: {e}")


    # 5. 게임 종료
    def is_game_over(self) -> tuple[bool, Optional[str]]:
        """
        게임 종료 조건을 확인합니다.
        Returns:
            (is_over: bool, winner: Optional[str])
        """
        mafia_count = sum(1 for s in self.agent_info.values() if s.alive and s.role == Role.MAFIA)
        others_count = sum(1 for s in self.agent_info.values() if s.alive and s.role != Role.MAFIA)

        if mafia_count == 0:
            return True, "CITIZENS"
        elif mafia_count >= others_count:
            return True, "MAFIA"
        else:
            return False, None

    # 6. 게임 결과
    async def announce_winner(self, winner: str):
        msg = json.dumps({
            "type": MessageType.GAME_RESULT.name,
            "payload": {
                "message": f"🏁 게임 종료! 승리 팀: {winner}",
                "winner": winner
            }
        })
        await self.broadcast_to_all(msg)
        print(f"🏁 게임 종료! 승리 팀: {winner}")
           

    async def broadcast_to_roles(self, user_text: str, roles: list[Role] = None ) -> None:
        """
        특정 역할을 가진 에이전트들에게만 메시지를 브로드캐스트합니다.
        
        Args:
            roles: 역할 문자열 리스트 (예: ["mafia", "detective"])
            user_text: 보낼 메시지 내용
        """
        if not self.executor:
            print("❌ Executor가 설정되어 있지 않습니다.")
            return

        for agent_name, status in self.agent_info.items():
            if roles and status.role not in roles: 
                continue  # 역할이 매칭되지 않으면 skip
            
            if not status.alive :
                continue # Alive가 아니면 skip

            print(f"\n🎯 '{agent_name}' ({status.role})에게 메시지를 전송 중...")
            await self.executor.send_to_other(agent_name, user_text)
   

    async def broadcast_to_all(self, user_text: str ) -> None:
        """
        특정 역할을 가진 에이전트들에게만 메시지를 브로드캐스트합니다.
        
        Args:
            user_text: 보낼 메시지 내용
        """
        if not self.executor:
            print("❌ Executor가 설정되어 있지 않습니다.")
            return

        for agent_name, status in self.agent_info.items():
           
            print(f"\n🎯 '{agent_name}' ({status.role})에게 메시지를 전송 중...")
            await self.executor.send_to_other(agent_name, user_text)
    
    #
    def handle_message(self, message: str) -> str: 
        # TODO
        logger.info(f"📩 ManagerAgent received message: {message}")
        return "Manager does not respond to messages."


