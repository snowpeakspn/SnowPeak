from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from database import db
from models import Product, Customer, Invoice, InvoiceItem
from utils import round_money, gst_split, next_invoice_number
from io import BytesIO
from weasyprint import HTML
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'change-this'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///granito.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

app = create_app()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/products", methods=["GET", "POST"])
def products():
    if request.method == "POST":
        p = Product(
            sku=request.form["sku"],
            name=request.form["name"],
            description=request.form.get("description", ""),
            unit=request.form.get("unit", "box"),
            price=float(request.form["price"]),
            gst_rate=float(request.form.get("gst_rate", 18)),
            stock_qty=float(request.form.get("stock_qty", 0))
        )
        db.session.add(p)
        db.session.commit()
        flash("Product saved", "success")
        return redirect(url_for("products"))
    items = Product.query.order_by(Product.name).all()
    return render_template("products.html", items=items)

@app.route("/customers", methods=["GET", "POST"])
def customers():
    if request.method == "POST":
        c = Customer(
            name=request.form["name"],
            phone=request.form.get("phone", ""),
            email=request.form.get("email", ""),
            address=request.form.get("address", ""),
            gstin=request.form.get("gstin", "")
        )
        db.session.add(c)
        db.session.commit()
        flash("Customer saved", "success")
        return redirect(url_for("customers"))
    items = Customer.query.order_by(Customer.name).all()
    return render_template("customers.html", items=items)

@app.route("/invoices")
def invoices():
    items = Invoice.query.order_by(Invoice.created_at.desc()).all()
    return render_template("invoices.html", items=items)

@app.route("/invoice/new", methods=["GET", "POST"])
def invoice_new():
    products = Product.query.filter_by(active=True).order_by(Product.name).all()
    customers = Customer.query.order_by(Customer.name).all()

    if request.method == "POST":
        customer_id = int(request.form["customer_id"])
        discount_pct = float(request.form.get("discount_pct", 0.0))
        is_interstate = request.form.get("is_interstate") == "on"

        # Invoice number
        last = Invoice.query.order_by(Invoice.id.desc()).first()
        prefix = "SP-2025"
        last_number = last.number if last else None
        number = next_invoice_number(prefix, last_number)

        inv = Invoice(number=number, customer_id=customer_id, discount_pct=discount_pct)
        db.session.add(inv)
        db.session.flush()  # get inv.id

        # Parse items
        subtotal = 0.0
        tax_total = 0.0

        rows = int(request.form["rows"])
        for i in range(rows):
            pid = int(request.form[f"pid_{i}"])
            qty = float(request.form[f"qty_{i}"])
            product = Product.query.get(pid)
            rate = float(request.form.get(f"rate_{i}", product.price))
            gst_rate = float(request.form.get(f"gst_{i}", product.gst_rate))

            line_subtotal = round_money(qty * rate)
            line_tax = round_money(line_subtotal * gst_rate / 100)
            line_total = round_money(line_subtotal + line_tax)

            ii = InvoiceItem(
                invoice_id=inv.id,
                product_id=pid,
                description=product.name,
                qty=qty,
                unit=product.unit,
                rate=rate,
                gst_rate=gst_rate,
                line_subtotal=line_subtotal,
                line_tax=line_tax,
                line_total=line_total
            )
            db.session.add(ii)

            # Adjust stock
            product.stock_qty = round_money(product.stock_qty - qty)

            subtotal += line_subtotal
            tax_total += line_tax

        # Discount
        discount_amount = round_money(subtotal * discount_pct / 100)
        taxable_value = round_money(subtotal - discount_amount)

        cgst, sgst, igst = gst_split(is_interstate, tax_total)

        total = round_money(taxable_value + cgst + sgst + igst)

        inv.subtotal = round_money(subtotal)
        inv.discount_amount = discount_amount
        inv.taxable_value = taxable_value
        inv.cgst = cgst
        inv.sgst = sgst
        inv.igst = igst
        inv.total = total
        inv.notes = request.form.get("notes", "")

        db.session.commit()
        flash(f"Invoice {inv.number} created", "success")
        return redirect(url_for("invoices"))

    return render_template("invoice_form.html", products=products, customers=customers)

@app.route("/invoice/<int:invoice_id>/pdf")
def invoice_pdf(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    html = render_template("invoice_pdf.html", inv=inv)
    pdf = HTML(string=html).write_pdf()
    return send_file(BytesIO(pdf), as_attachment=True, download_name=f"{inv.number}.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
