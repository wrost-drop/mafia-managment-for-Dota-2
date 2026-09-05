from .models import Role

def role_distribution(player_count: int) -> dict[Role, int]:
    if not 8 <= player_count <= 15:
        raise ValueError("A game requires from 8 to 15 players.")
    mafia = 2 if player_count <= 10 else 3 if player_count <= 13 else 4
    special = 2 if player_count in {13, 14, 15} else 1
    return {
        Role.MAFIA: mafia,
        Role.SHERIFF: 1,
        Role.DOCTOR: 1,
        Role.SPECIAL: special,
        Role.CIVILIAN: player_count - mafia - 2 - special,
    }
