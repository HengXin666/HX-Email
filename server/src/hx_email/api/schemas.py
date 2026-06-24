from pydantic import BaseModel, ConfigDict


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
    imap_password: str = ""
    client_id: str = ""
    refresh_token: str = ""
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


class AccountTextImport(BaseModel):
    text: str
    duplicate_strategy: str = "skip"


class TokenToolPrepare(BaseModel):
    client_id: str
    redirect_uri: str
    scope: str = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
    tenant: str = "consumers"
    prompt_consent: bool = True


class TokenToolExchange(BaseModel):
    code: str = ""
    state: str = ""
    callback_url: str = ""


class TokenToolSave(BaseModel):
    mode: str = "update"
    account_id: int | None = None
    email: str = ""
    client_id: str
    refresh_token: str


class TokenToolConfigWrite(BaseModel):
    client_id: str = ""
    redirect_uri: str = ""
    scope: str = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
    tenant: str = "consumers"
    prompt_consent: bool = True


class SettingsUpdate(BaseModel):
    """Any subset of settings fields as key-value pairs."""

    model_config = ConfigDict(extra="allow")


class CronValidateRequest(BaseModel):
    cron_expression: str


class TelegramTestRequest(BaseModel):
    bot_token: str = ""
    chat_id: str = ""
    proxy_url: str | None = None


class EmailTestRequest(BaseModel):
    recipient: str
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None


class WebhookTestRequest(BaseModel):
    url: str
    token: str | None = None


class VerificationAITestRequest(BaseModel):
    subject: str | None = None
    body: str | None = None
    body_html: str | None = None
    code_length: int | None = None
    code_regex: str | None = None


class RefreshSelectedRequest(BaseModel):
    account_ids: list[int]


class BatchEmailRequest(BaseModel):
    account_ids: list[int]
    folders: list[str] | None = None
    skip: int = 0
    top: int = 20


class DeleteEmailRequest(BaseModel):
    email: str
    ids: list[str]


class CFWorkerSyncRequest(BaseModel):
    worker_url: str = ""
    admin_key: str = ""


class AccountUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    client_id: str | None = None
    refresh_token: str | None = None
    group_id: int | None = None
    remark: str | None = None
    status: str | None = None
    provider: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None


class RemarkUpdate(BaseModel):
    remark: str


class BatchGroupUpdate(BaseModel):
    account_ids: list[int]
    group_id: int


class BatchDelete(BaseModel):
    account_ids: list[int]


class BatchStatusUpdate(BaseModel):
    account_ids: list[int]
    status: str


class BatchNotificationToggle(BaseModel):
    account_ids: list[int]
    enabled: bool


class BatchTagAction(BaseModel):
    account_ids: list[int]
    tag_id: int
    action: str  # "add" or "remove"


class ExportVerify(BaseModel):
    password: str


class ExportSelected(BaseModel):
    group_ids: list[int]
    verify_token: str | None = None


class PoolAdminAction(BaseModel):
    action: (
        str  # claim/release/complete/freeze/unfreeze/cooldown/retire/add_to_pool/remove_from_pool
    )
    caller_id: str | None = None
    task_id: str | None = None
    reason: str | None = None


class TelegramToggle(BaseModel):
    enabled: bool
