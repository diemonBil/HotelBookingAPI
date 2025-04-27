import requests
from django.conf import settings

""" Sends a request to Monobank API to create a payment invoice for the given Payment object """
def create_monobank_invoice(payment):
    # Define request headers including your Monobank merchant token
    headers = {
        "X-Token": settings.MONOBANK_TOKEN,
        "Content-Type": "application/json"
    }

    # Prepare the data payload for the invoice request
    data = {
        # Amount must be in kopecks (e.g. 150 UAH = 15000)
        "amount": int(payment.amount * 100),
        # Currency code for UAH (Ukrainian Hryvnia)
        "ccy": 980,
        "initiationKind": "client",
        "merchantPaymInfo": {
            # Unique invoice identifier (used to track payment status)
            "reference": payment.invoice_id,
            # Message shown to the user in the Monobank payment interface
            "destination": "Оплата комунальних за Флоркевич Павло кв 28.1",
            # Caption title shown at the top of the payment screen
            "caption": "Bill payment",
        },
        # Where the user will be redirected after completing the payment
        "redirectUrl": "https://6622-146-0-81-231.ngrok-free.app/api/v1/payment-success/",
        # Where Monobank will send a POST request with payment result
        "webHookUrl": "https://6622-146-0-81-231.ngrok-free.app/api/v1/payment/update-status/"
    }

    # Send the POST request to Monobank to create the invoice
    response = requests.post(
        "https://api.monobank.ua/api/merchant/invoice/create",
        json=data,
        headers=headers
    )

    # Return the response data (should include invoiceId and pageUrl)
    return response.json()