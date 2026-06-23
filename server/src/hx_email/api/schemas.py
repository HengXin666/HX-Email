from pydantic import BaseModel


class Credentials(BaseModel):
    username: str
    password: str


class RegistrationSettingUpdate(BaseModel):
    enabled: bool


class UsableEmailCreate(BaseModel):
    address: str
    label: str = ""


class MailPoolEntryCreate(BaseModel):
    usable_email_id: int


class MailPoolClaimRequest(BaseModel):
    project_key: str
    claim_key: str = ""


class MailPoolCompleteRequest(BaseModel):
    project_key: str


class TempMailboxCreate(BaseModel):
    address: str | None = None
    label: str = ""


class EmailAccountCreate(BaseModel):
    provider: str
    primary_address: str
    display_name: str
    imap_host: str = ""
    imap_port: int | None = None
    username: str = ""
    alias_addresses: list[str] = []


class AliasCreate(BaseModel):
    address: str
    label: str = ""


class GroupCreate(BaseModel):
    name: str
    color: str = "#58a6ff"


class TagCreate(BaseModel):
    name: str
    color: str = "#238636"


class PlatformWrite(BaseModel):
    name: str


class PlatformBindingCreate(BaseModel):
    platform_id: int
    status: str = "active"
    notes: str = ""


class PlatformBindingUpdate(BaseModel):
    status: str
    notes: str = ""


class PlatformCandidateRequest(BaseModel):
    sender: str = ""
    subject: str = ""
    body: str = ""


class UsableEmailOrganization(BaseModel):
    label: str | None = None
    group_id: int | None = None
    tag_ids: list[int] = []
