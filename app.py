# Invoice prefix set to SP-25
prefix = "SP-25"
last = Invoice.query.order_by(Invoice.id.desc()).first()
last_number = last.number if last else None
number = next_invoice_number(prefix, last_number)
