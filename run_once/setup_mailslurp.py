# run_once/setup_mailslurp.py
import mailslurp_client
from django.conf import settings

def setup_mailslurp():
    configuration = mailslurp_client.Configuration()
    configuration.api_key["x-api-key"] = settings.MAILSLURP_API_KEY

    with mailslurp_client.ApiClient(configuration) as api_client:

        # create inbox
        inbox_api = mailslurp_client.InboxControllerApi(api_client)
        inbox = inbox_api.create_inbox()

        print(f"Inbox ID   : {inbox.id}")
        print(f"Email Address: {inbox.email_address}")
        # save these in .env

        # create webhook for this inbox
        webhook_api = mailslurp_client.WebhookControllerApi(api_client)
        webhook = webhook_api.create_webhook(
            inbox_id=inbox.id,
            create_webhook_options=mailslurp_client.CreateWebhookOptions(
                url="https://your-ngrok-url.ngrok-free.dev/email/webhook/",
                event_name="NEW_EMAIL",
            )
        )
        print(f"Webhook ID: {webhook.id}")