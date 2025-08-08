import json
from enum import Enum, auto
from typing import Dict
from typing import Optional

class Role(Enum):
    MAFIA = auto()
    DETECTIVE = auto()
    VILLAGER = auto()

class MessageType(Enum):
    ROLE_ASSIGNMENT = auto()
    INTRO_REQUEST = auto()
    INTRO_RESPONSE = auto()
    DAY_ACTION_REQUEST = auto()
    VOTE_REQUEST = auto()
    VOTE_RESPONSE = auto()
    EXECUTION_RESULT = auto()
    KILLED_RESULT = auto()
    NIGHT_ACTION_REQUEST = auto()
    NIGHT_ACTION_RESULT = auto()
    GAME_RESULT = auto()
    QUESTION = auto()
    QUESTION_RESPONSE = auto()

def create_message(message_type: MessageType, from_name: str, to_name: str,
                   round: Optional[int] = None,
                   role: Optional[Role] = None,
                   target: Optional[str] = None,
                   is_mafia: Optional[bool] = None,
                   winner: Optional[str] = None) -> str:

    # 기본 payload 구조
    payload = {
        "from": from_name,
        "to": to_name
    }

    # 메시지 유형별 처리
    if message_type == MessageType.ROLE_ASSIGNMENT:
        role_messages = {
            Role.MAFIA: "😈 당신은 마피아입니다. 밤마다 한 명을 제거할 수 있습니다.",
            Role.DETECTIVE: "🕵️ 당신은 경찰입니다. 밤마다 한 명의 정체를 확인할 수 있습니다.",
            Role.VILLAGER: "👨‍🌾 당신은 시민입니다. 토론을 통해 마피아를 찾아내세요."
        }
        payload.update({
            "message": role_messages[role],
            "role": role.name
        })

    elif message_type == MessageType.INTRO_REQUEST:
        payload["message"] = "🌞 첫째날 낮이 되었습니다. 모두 자기소개를 해주세요."

    elif message_type == MessageType.DAY_ACTION_REQUEST:
        payload["message"] = "🌞 낮이 되었습니다. 자유롭게 토론하고, 누가 의심스러운지 누가 마피아인지 후보를 선정해주세요.."

    elif message_type == MessageType.VOTE_REQUEST:
        payload["message"] = "🗳️ 누구를 처형할지 투표해주세요. 살아있는 에이전트 이름 중에서 선택하세요."

    elif message_type == MessageType.EXECUTION_RESULT:
        payload.update({
            "message": f"🔪 {target} 가 투표로 처형되었습니다.",
            "executed": target
        })

    elif message_type == MessageType.KILLED_RESULT:
        payload.update({
            "message": f"💀 밤 사이 {target} 가 사망했습니다.",
            "killed": target
        })

    elif message_type == MessageType.NIGHT_ACTION_REQUEST:
        role_messages = {
            Role.MAFIA: "밤입니다. 제거할 대상을 선택하세요.",
            Role.DETECTIVE: "밤입니다. 조사할 대상을 선택하세요."
        }
        payload.update({
            "message": role_messages[role],
            "role": role.name
        })

    elif message_type == MessageType.NIGHT_ACTION_RESULT:
        payload.update({
            "message": f"🔍 당신이 조사한 {target} 은(는) {'마피아' if is_mafia else '시민'}입니다.",
            "target": target,
            "is_mafia": is_mafia
        })

    elif message_type == MessageType.GAME_RESULT:
        payload.update({
            "message": f"🏁 게임 종료! 승리 팀: {winner}",
            "winner": winner
        })

    else:
        payload["message"] = "❓ 정의되지 않은 메시지입니다."

    return json.dumps({
        "type": message_type.name,
        "payload": payload
    })



def create_chat_message(message_type: MessageType, from_name: str, to_name: str,
                    text: Optional[str] = None   ) -> str:

    # 기본 payload 구조
    payload = {
        "from": from_name,
        "to": to_name
    }

    # 메시지 유형별 처리
    if message_type == MessageType.INTRO_RESPONSE:
        payload.update({
            "message": f"{text}"
        })
    elif message_type == MessageType.QUESTION:
        payload.update({
            "message": f"{to_name}, 방금 메시지가 이상해 보여요. 설명해주세요."
        })
    elif message_type == MessageType.QUESTION_RESPONSE:
        payload.update({
            "message": f"{text}"
        })

    else:
        payload["message"] = "❓ 정의되지 않은 메시지입니다."

    return json.dumps({
        "type": message_type.name,
        "payload": payload
    })

 