import os
import asyncio
import logging
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from .a2a_client import A2AClientAgent
from .a2a_client import A2AServerEntry
from base_agent import BaseAgent


logger = logging.getLogger(__name__)


class GenericAgentExecutor(AgentExecutor):

    def __init__(self,
        agent: BaseAgent,
        remote_agent_entries: list[A2AServerEntry]
    ):   
        self.agent = agent
        self.client_agent = A2AClientAgent(remote_agent_entries)

        # 등록된 에이전트 이름만 추출
        self.other_agentes = [entry.name for entry in remote_agent_entries]
        self.agent.initialize(self.other_agentes, self) #  executor (self) 전달

            
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:

        logger.info(f'Executing agent {self.agent.agent_name}')

        rcvRequest = context._params
        #print("Request :", rcvRequest.model_dump(mode='json', exclude_none=False))
        print()
        # 1. get user input message 
        text = context.get_user_input()
        task = context.current_task
        print("Recv Request :", text)

        # 2. 
        response_text = await self.agent.handle_message( text )

        # 3. 응답 전송
        await event_queue.enqueue_event(new_agent_text_message(response_text))
    
    
    async def send_to_other(self, agent_name:str, user_text:str) -> None:
        
        if agent_name not in self.client_agent.remote_agent_connections:
            print(f"❌ 에이전트 '{agent_name}' 을 찾을 수 없습니다.")
            
            # remote_server_enties에서 agent_name을 찾아서, 연결한다. 
            try:
                # remote_agent_entries에서 name으로 등록 시도
                await self.client_agent.retrieve_card_by_name(agent_name)
            except ValueError as e:
                print(f"❌ 에이전트 연결 실패: {e}")
                return
            
            
            # 연결 성공 여부 재확인
            if agent_name not in self.client_agent.remote_agent_connections:
                print(f"❌ 에이전트 '{agent_name}' 연결 실패 (등록 후에도 연결 없음).")
                return
            else:
                print(f"✅ 에이전트 '{agent_name}' 연결 완료.")

           
        response = await self.client_agent.send_message(agent_name, None, None, user_text)
        print("Response:")
        if response : 
            for i, item in enumerate(response):
                print(f"  {item}")
                
        else : 
            print("⚠️ 응답이 없습니다 (response is None).")
            print()

        return response


    async def broadcast_to_roles(self, roles: list[str], user_text: str) -> None:
        """
        특정 역할을 가진 에이전트들에게만 메시지를 브로드캐스트합니다.
        
        Args:
            roles: 역할 문자열 리스트 (예: ["mafia", "detective"])
            user_text: 보낼 메시지 내용
        """
        for agent_name, role in self.agent.agent_roles.items():
            if role not in roles:
                continue  # 역할이 매칭되지 않으면 skip

            print(f"\n🎯 '{agent_name}' ({role})에게 메시지를 전송 중...")
            self.send_to_other(agent_name, user_text)

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception('cancel not supported')