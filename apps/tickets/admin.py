from django.contrib import admin
from .models import Ticket, TicketInfraction, TicketProof
admin.site.register(Ticket)
admin.site.register(TicketInfraction)
admin.site.register(TicketProof)
