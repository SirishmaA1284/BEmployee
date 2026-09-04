import enum


class BusinessRole(str, enum.Enum):
    """A user's role within one specific business (per business_members row).

    Role is per (user_id, business_id), not global on the user — one person
    can be OWNER of one business and EMPLOYEE of another.
    """

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"
