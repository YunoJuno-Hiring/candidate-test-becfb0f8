# Webhook events this app emits. Each app builds its own payloads; the webhooks app only delivers them.
from webhooks.models import EventType
from webhooks.services import emit

from .models import Contract


def emit_contract_created(contract: Contract) -> None:
    # Thin on purpose: no names or rates. The full contract is behind the download link, not in the payload.
    emit(
        contract.company,
        EventType.CONTRACT_CREATED,
        {
            'id': contract.id,
            'status': contract.status,
            'start_date': str(contract.start_date),
            'end_date': str(contract.end_date),
            # Deliberately fake: stands in for a short-lived signed link to the contract PDF in object storage.
            'download_url': 'https://fake-bucket.examplecloud.com/fake.pdf?signature=fake',
        },
    )
