from hx_email.server.mail.email_accounts import EmailAccount
from hx_email.server.mail.mail_pool import MailPoolEntry
from hx_email.server.mail.temp_mail import TempMailbox
from hx_email.server.mail.usable_emails import UsableEmail
from hx_email.server.mail.verification import VerificationMatch, VerificationReading
from hx_email.server.workspace.platforms import Platform, PlatformBinding, PlatformCandidate
from hx_email.server.workspace.workbench import Group, Tag, WorkbenchEmail


def serialize_usable_email(usable_email: UsableEmail) -> dict[str, object]:
    return {
        "id": usable_email.id,
        "address": usable_email.address,
        "label": usable_email.label,
        "kind": usable_email.kind,
        "status": usable_email.status,
    }


def serialize_group(group: Group | None) -> dict[str, object] | None:
    if group is None:
        return None
    return {"id": group.id, "name": group.name, "color": group.color}


def serialize_tag(tag: Tag) -> dict[str, object]:
    return {"id": tag.id, "name": tag.name, "color": tag.color}


def serialize_platform(platform: Platform) -> dict[str, object]:
    return {"id": platform.id, "name": platform.name}


def serialize_platform_binding(binding: PlatformBinding) -> dict[str, object]:
    return {
        "id": binding.id,
        "usable_email_id": binding.usable_email_id,
        "platform": serialize_platform(binding.platform),
        "status": binding.status,
        "notes": binding.notes,
    }


def serialize_platform_candidate(candidate: PlatformCandidate) -> dict[str, object]:
    return {"name": candidate.name, "source": candidate.source}


def serialize_workbench_email(usable_email: WorkbenchEmail) -> dict[str, object]:
    return {
        "id": usable_email.id,
        "address": usable_email.address,
        "label": usable_email.label,
        "kind": usable_email.kind,
        "status": usable_email.status,
        "group": serialize_group(usable_email.group),
        "tags": [serialize_tag(tag) for tag in usable_email.tags],
        "platform_binding_count": usable_email.platform_binding_count,
    }


def serialize_temp_mailbox(mailbox: TempMailbox) -> dict[str, object]:
    return {
        "id": mailbox.usable_email_id,
        "address": mailbox.address,
        "label": mailbox.label,
        "kind": "temp",
        "status": mailbox.status,
        "provider": mailbox.provider,
        "email_account_id": mailbox.email_account_id,
    }


def serialize_email_account(account: EmailAccount) -> dict[str, object]:
    return {
        "id": account.id,
        "provider": account.provider,
        "primary_address": account.primary_address,
        "display_name": account.display_name,
        "status": account.status,
        "primary_usable_email": serialize_usable_email(account.primary_usable_email),
        "usable_emails": [
            serialize_usable_email(usable_email) for usable_email in account.usable_emails
        ],
    }


def serialize_mail_pool_entry(entry: MailPoolEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "usable_email": serialize_usable_email(entry.usable_email),
        "status": entry.status,
        "claim_key": entry.claim_key,
        "claimed_project_key": entry.claimed_project_key,
        "completed_project_key": entry.completed_project_key,
    }


def serialize_verification_match(match: VerificationMatch) -> dict[str, object]:
    return {
        "code": match.code,
        "link": match.link,
        "recipient_address": match.recipient_address,
        "certainty": match.certainty,
        "subject": match.subject,
    }


def serialize_verification_reading(reading: VerificationReading) -> dict[str, object]:
    return {
        "usable_email": serialize_usable_email(reading.usable_email),
        "matches": [serialize_verification_match(match) for match in reading.matches],
    }
