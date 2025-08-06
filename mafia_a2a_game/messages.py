from enum import Enum, auto
from typing import Dict

class Role(Enum):
    MAFIA = auto()
    DETECTIVE = auto()
    VILLAGER = auto()

class MessageType(Enum):
    ROLE_ASSIGNMENT = auto()
    INTRO_REQUEST = auto()
    INTRO_RESPONSE = auto()
    VOTE_REQUEST = auto()
    VOTE_RESPONSE = auto()
    EXECUTION_RESULT = auto()
    KILLED_RESULT = auto()
    NIGHT_ACTION_REQUEST = auto()
    NIGHT_ACTION_RESULT = auto()
    GAME_RESULT = auto()
    QUESTION = auto()
    QUESTION_RESPONSE = auto()

def create_role_assignment_message(role: Role) -> Dict:
    role_messages = {
        Role.MAFIA: "😈 당신은 마피아입니다. 밤마다 한 명을 제거할 수 있습니다.",
        Role.DETECTIVE: "🕵️ 당신은 경찰입니다. 밤마다 한 명의 정체를 확인할 수 있습니다.",
        Role.VILLAGER: "👨‍🌾 당신은 시민입니다. 토론을 통해 마피아를 찾아내세요."
    }

    return {
        "type": MessageType.ROLE_ASSIGNMENT.name,
        "payload": {
            "role": role.name,
            "message": role_messages[role]
        }
    }