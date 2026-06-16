from io import BytesIO
from barcode import Code128
from barcode.writer import ImageWriter
from django.core.files.base import ContentFile

def generate_ticket_barcode(ticket):
    value = f"SMR-{ticket.id:08d}"
    buff = BytesIO()
    Code128(value, writer=ImageWriter()).write(buff)
    ticket.barcode_value = value
    ticket.barcode_image.save(f"{value}.png", ContentFile(buff.getvalue()), save=False)
