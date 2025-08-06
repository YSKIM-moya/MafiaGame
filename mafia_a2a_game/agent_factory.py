from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
import httpx
import os


from a2a_core.config_loader import load_a2a_config
from a2a_core.config_loader import get_server_list
from a2a_core.a2a_client import A2AServerEntry
from a2a_core.server_executor import GenericAgentExecutor
from manager_agent import ManagerAgent
from member_agent import MemberAgent


def get_agent(agent_card: AgentCard):
    """Get the agent, given an agent card."""
    try:
        if agent_card.name == 'Manager Agent':
            return ManagerAgent()
        else :
            return MemberAgent(agent_card.name, agent_card.description) 
            
    except Exception as e:
        raise e


def build_server_from_config(config_file:str) :
    # 경로 분리
    config_dir = os.path.dirname(config_file)
    file_name = os.path.basename(config_file)
    print(f"📁 config_dir: {config_dir}")
    print(f"📄 file_name: {file_name}")

    # 1. get my own server config 
    server_config = load_a2a_config(config_file)

    # 2. get the otheres config
    other_server_entries = get_server_list(config_dir, file_name)
    
    # 3. build server agent 
    app, handler = build_agent_from_config(server_config, other_server_entries)
    return server_config, app, handler


def build_agent_from_config(config: dict, other_server_entries: list[A2AServerEntry]) -> tuple[str, A2AStarletteApplication]:
    host = config["host"]
    port = config["port"]
    url = f"http://{host}:{port}/"

    skills = [
        AgentSkill(**skill) for skill in config.get("skills", [])
    ]

    capabilities = AgentCapabilities(**config.get("capabilities", {}))

    agent_card = AgentCard(
        name=config["name"],
        description=config["description"],
        url=url,
        version=config["version"],
        defaultInputModes=config.get("defaultInputModes", ["text"]),
        defaultOutputModes=config.get("defaultOutputModes", ["text"]),
        capabilities=capabilities,
        skills=skills,
    )


    # PushNotification 
    #httpx_client = httpx.AsyncClient()
    #push_config_store = InMemoryPushNotificationConfigStore()
    #push_sender = BasePushNotificationSender(httpx_client=httpx_client, 
    #                                        config_store=push_config_store)

    executor  = GenericAgentExecutor(agent=get_agent(agent_card),
                                    remote_agent_entries=other_server_entries)

    #await executor.asyn_initialize()

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore()
    )  

    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler
    )

    print(f"Starting {config["name"]} server on  http://{host}:{port}")
    

    return app.build(), handler
