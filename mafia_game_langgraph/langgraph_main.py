import logging
import os
import sys

import uvicorn
import asyncio
import nest_asyncio  # 중첩 루프 허용

from typing import Callable
from agent_factory import build_server_from_config
from langgraph_manager_agent import LangGraphManagerAgent
from member_agent import MemberAgent

server = None  # 전역 서버 객체

def shutdown_server():
    global server
    if server:
        print("🛑 서버 종료 요청 수신됨. 서버를 종료합니다.")
        server.should_exit = True


async def main(config_path: str):
    """Starts the Test Agent with A2A protocol."""

    global server

    # 1. 에이전트 설정 및 서버 빌드
    # Get My Own Server Config and Other Server List
    server_config, app, handler = build_server_from_config(config_path)
    
    host = server_config["host"]
    port = server_config["port"]
    name = server_config["name"]
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    print(f"✅ {name} A2A Server is running at http://{host}:{port}/")
   
    # 2. 서버 실행 (비동기))
    server_task = asyncio.create_task(server.serve())

    # 3. 모든 에이전트에 shutdown 콜백 등록
    agent = handler.agent_executor.agent
    if isinstance(agent, (LangGraphManagerAgent, MemberAgent)):
        agent.set_server_shutdown_callback(shutdown_server)

    # 4. ManagerAgent라면 게임 루프 시작 
    if name == "Manager Agent":
        await asyncio.sleep(2)  # 모든 서버가 뜰 시간을 약간 확보
        initial_state = {
            "agent_info" : {}, 
            "round" : 1, 
            "game_over" : False, 
            "winner" : {}
        }
        await agent.start_game(initial_state)

    # 5. 서버 종료 대기
    await server_task

    
   

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <path_to_config.json>")
        sys.exit(1)

    config_path = sys.argv[1]
    
    try:
        asyncio.run(main(config_path))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("👋 서버가 정상적으로 종료되었습니다.")
