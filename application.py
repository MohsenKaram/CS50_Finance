import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Extract the current cash balance for the user
    cash = db.execute("SELECT cash FROM users WHERE id = :usrid",
                      usrid=session["user_id"])[0]['cash']

    # Extract the current portfolio for the user
    inforg = db.execute("SELECT t1.symbol AS symbol, (COALESCE(s_shares_buy,0)-COALESCE(s_shares_sell,0)) AS shares FROM (SELECT symbol, SUM(SHARES) AS 's_shares_buy' FROM txn WHERE (user_id=:usrid AND txtype=1) GROUP BY SYMBOL) t1 LEFT JOIN (SELECT symbol, SUM(SHARES) AS 's_shares_sell' FROM txn WHERE (user_id=:usrid AND txtype=0) GROUP BY SYMBOL) t2 ON (t1.symbol = t2.symbol) WHERE SHARES>0",
                        usrid=session["user_id"])
    info = []

    # Look up the company name and the current price for each owned symbol
    if len(inforg) > 0:
        for i in range(len(inforg)):
            skinfo = lookup(inforg[i]['symbol'])
            info.append({**inforg[i], **skinfo})
    else:
        info = None

    return render_template("index.html", info=info, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    cash = db.execute("SELECT cash FROM users WHERE id = :usrid",
                      usrid=session["user_id"])[0]['cash']

    render_template("buy.html", cash=cash)

    if request.method == "POST":

        # Ensure stock symbol is submitted
        if not request.form.get("symbol"):
            return apology("you must provide a Stock symbol")

        # Ensure number of shares is submitted
        if not request.form.get("shares").isdigit() or not int(request.form.get("shares")) > 0:
            return apology("you must provide a valid number of shares")

        # Getting the symbol info
        qinfo = lookup(request.form.get("symbol"))

        # Ensure stock symbol is valid and known
        if not qinfo:
            return apology("invalid or unknown stock's symbol")


        # Calculate the transaction amount
        amount = int(request.form.get("shares")) * qinfo['price']

        # Ensure that the user has available balance to make the purchase
        if amount > cash:
            return apology("insufficient funds")
        # Execute the transaction
        else:
            # Update the user cash in users table
            db.execute("UPDATE users SET cash = :nvalue WHERE id = :usrid",
                       nvalue=cash-amount, usrid=session["user_id"])
            # Insert the transaction details
            db.execute("INSERT INTO txn (symbol, txtype, shares, price, amount, user_id) VALUES (:sy, 1, :sh, :px, :am, :uid)",
                       sy=qinfo['symbol'], sh=int(request.form.get("shares")), px=qinfo['price'], am=amount, uid=session["user_id"])

        # Transaction success Redirect user to home page
        flash('Bought!')
        return redirect("/")
    else:
        return render_template("buy.html", cash=cash)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    info = db.execute("SELECT symbol, shares, price, CASE txtype WHEN 1 THEN 'Buy' ELSE 'Sell' END type, tdate FROM txn WHERE user_id=:usrid",
                      usrid=session["user_id"])

    return render_template("history.html", info=info)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure stock symbol is submitted
        if not request.form.get("symbol"):
            return apology("you must provide a Stock symbol")

        # Getting the symbol info
        qinfo = lookup(request.form.get("symbol"))

        # Ensure stock symbol is valid and known
        if not qinfo:
            return apology("invalid or unknown stock's symbol")

        # If success will render quoted.html passing the stock info to the template info
        else:
            return render_template("quoted.html", info=qinfo)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide a username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide a password", 400)

        # Ensure confirmation were submitted
        elif not request.form.get("confirmation"):
            return apology("must provide the password confirmation", 400)

        # Ensure password and confirmation are matching
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and the confirmation doesn't match", 400)

        user_id = db.execute("INSERT INTO users (username, hash) VALUES (:usname, :paswrd) ",
                             usname=request.form.get("username"), paswrd=generate_password_hash(request.form.get("password")))

        if user_id == None:
            return apology("username is already exits, please provide another one", 400)

        # Remember which user has logged in
        session["user_id"] = user_id

        flash("Your username: {} has registered successfully!".format(request.form.get("username")))

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/add", methods=["GET", "POST"])
@login_required
def addcash():
    """Get stock quote."""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure stock symbol is submitted
        if not request.form.get("cash"):
            return apology("you must provide a valid amount")

        cash = float(request.form.get("cash"))

        # Update the the user data by adding the submitted cash amount
        db.execute("UPDATE users SET cash = (cash + :am) WHERE id = :usrid", am=cash, usrid=session["user_id"])

        flash(f"An amount of ${cash:,.2f} added to your cash!")

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("add.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Extract the current portfolio for the user
    inforg = db.execute("SELECT t1.symbol AS symbol, (COALESCE(s_shares_buy,0)-COALESCE(s_shares_sell,0)) AS shares FROM (SELECT symbol, SUM(SHARES) AS 's_shares_buy' FROM txn WHERE (user_id=:usrid AND txtype=1) GROUP BY SYMBOL) t1 LEFT JOIN (SELECT symbol, SUM(SHARES) AS 's_shares_sell' FROM txn WHERE (user_id=:usrid AND txtype=0) GROUP BY SYMBOL) t2 ON (t1.symbol = t2.symbol) WHERE SHARES>0",
                        usrid=session["user_id"])

    # Ensure that the user has stocks
    if inforg == None:
        return apology("You must have stocks to sell")

    if request.method == "POST":

        # Ensure that the user selected a symbol from the list
        if not request.form.get("symbol"):
            return apology("Please choose a stock symbol to sell")
        else:
            # Getting the selected symbol name
            symbolname = request.form.get("symbol")

        i =  0
        for i in range(len(inforg)):
            if inforg[i]['symbol'] == symbolname:
                break

        # Ensure that the user has that many shares inputted to sell
        if not request.form.get("shares").isdigit() or not int(request.form.get("shares")) <= inforg[i]['shares']:
            return apology("the requested number of shares is greater than you holds or invalid")

        # Getting the symbol price
        stinfo = lookup(symbolname)

        # Calculating the transaction amount
        amount = stinfo['price'] * int(request.form.get("shares"))

        # Insert the transaction details
        db.execute("INSERT INTO txn (symbol, txtype, shares, price, amount, user_id) VALUES (:sy, 0, :sh, :px, :am, :uid)",
                   sy=symbolname, sh=int(request.form.get("shares")), px=stinfo['price'], am=amount, uid=session["user_id"])

        # Update the user cash in users table
        db.execute("UPDATE users SET cash = (cash + :nvalue) WHERE id = :usrid", nvalue=amount, usrid=session["user_id"])

        flash(f"You've successfully sold {stinfo['name']}'s stock @ price ${stinfo['price']:,.2f}")

        return redirect("/")
    else:
        return render_template("sell.html", info=inforg)


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
