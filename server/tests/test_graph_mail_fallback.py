from hx_email.config import Settings
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.graph.fallback_provider import FallbackMailProvider


class EmptyGraphResult:
    def __init__(self) -> None:
        self.messages: list[MailboxMessage] = []
        self.succeeded: bool = True


class EmptyGraphProvider:
    def __init__(self) -> None:
        self.calls: int = 0

    def read_messages_result(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        top: int = 50,
    ) -> object:
        self.calls += 1
        return EmptyGraphResult()


class FailingImapProvider:
    def __init__(self) -> None:
        self.calls: int = 0

    def read_messages(self, email_account: EmailAccountMailbox) -> list[MailboxMessage]:
        self.calls += 1
        raise AssertionError("Outlook Graph success with empty inbox must not fall back to IMAP")


def test_outlook_graph_empty_inbox_does_not_fall_back_to_imap(tmp_path) -> None:
    provider = FallbackMailProvider(Settings(data_dir=tmp_path))
    graph = EmptyGraphProvider()
    imap = FailingImapProvider()
    provider._graph = graph
    provider._imap = imap

    messages = provider.read_messages(
        EmailAccountMailbox(id=1, provider="outlook", primary_address="owner@example.com")
    )

    assert messages == []
    assert graph.calls == 1
    assert imap.calls == 0


def test_outlook_graph_failure_still_falls_back_to_imap(tmp_path) -> None:
    provider = FallbackMailProvider(Settings(data_dir=tmp_path))

    class FailingGraphProvider:
        def read_messages_result(
            self,
            email_account: EmailAccountMailbox,
            folder: str = "inbox",
            top: int = 50,
        ) -> object:
            raise RuntimeError("graph unavailable")

    class WorkingImapProvider:
        def read_messages(self, email_account: EmailAccountMailbox) -> list[MailboxMessage]:
            return [
                MailboxMessage(
                    recipient_address=email_account.primary_address,
                    subject="via imap",
                    body="body",
                )
            ]

    provider._graph = FailingGraphProvider()
    provider._imap = WorkingImapProvider()

    messages = provider.read_messages(
        EmailAccountMailbox(id=1, provider="outlook", primary_address="owner@example.com")
    )

    assert [message.subject for message in messages] == ["via imap"]
