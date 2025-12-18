from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_apscheduler import APScheduler
from config import Config
from models import db, User, Broker, BrokerRating, Investment, Portfolio, Stock, PortfolioStock, PriceHistory, Message
from datetime import datetime, date

app = Flask(__name__)
app.config.from_object(Config)

# Scheduler configuration
app.config['SCHEDULER_API_ENABLED'] = True

db.init_app(app)

# Initialize scheduler
scheduler = APScheduler()
scheduler.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, inicia sesion para acceder.'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==================== SCHEDULED TASKS ====================

def update_prices_from_iol():
    """Background task to update stock prices from IOL every 30 minutes"""
    with app.app_context():
        from iol_service import iol_service, DEFAULT_BONDS
        
        print(f"[SCHEDULER] Actualizando precios desde IOL - {datetime.now().strftime('%H:%M:%S')}")
        
        stocks = Stock.query.all()
        if not stocks:
            # Create default bonds if none exist
            for symbol in DEFAULT_BONDS:
                stock = Stock(
                    symbol=symbol,
                    name=symbol,
                    stock_type='bono',
                    market='BCBA',
                    currency='ARS'
                )
                db.session.add(stock)
            db.session.commit()
            stocks = Stock.query.all()
        
        symbols = [s.symbol for s in stocks]
        prices = iol_service.get_multiple_prices(symbols)
        
        updated = 0
        for symbol, price_data in prices.items():
            stock = Stock.query.filter_by(symbol=symbol).first()
            if stock and price_data.get('price'):
                stock.current_price = float(price_data['price'])
                stock.last_updated = datetime.utcnow()
                
                # Save to history (one per day)
                existing_history = PriceHistory.query.filter_by(stock_id=stock.id, date=date.today()).first()
                if existing_history:
                    existing_history.price = stock.current_price
                else:
                    history = PriceHistory(stock_id=stock.id, price=stock.current_price, date=date.today())
                    db.session.add(history)
                
                updated += 1
        
        db.session.commit()
        print(f"[SCHEDULER] {updated} precios actualizados")


# Schedule the job to run every 30 minutes
@scheduler.task('interval', id='update_iol_prices', minutes=30, misfire_grace_time=900)
def scheduled_price_update():
    update_prices_from_iol()




# ==================== AUTHENTICATION ====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('¡Bienvenido de vuelta!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        
        if User.query.filter_by(username=username).first():
            flash('El usuario ya existe', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('El email ya está registrado', 'error')
            return render_template('register.html')
        
        user = User(username=username, email=email, full_name=full_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('¡Cuenta creada exitosamente! Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('login'))


# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    # Get statistics
    total_investments = Investment.query.filter_by(status='active').count()
    total_brokers = Broker.query.count()
    
    # Calculate total invested
    investments = Investment.query.filter_by(status='active').all()
    total_invested_ars = sum(i.amount for i in investments if i.currency == 'ARS')
    total_invested_usd = sum(i.amount for i in investments if i.currency == 'USD')
    
    # Calculate expected returns from plazo fijo
    plazo_fijo_return = sum(i.calculated_return for i in investments if i.investment_type == 'plazo_fijo')
    
    # Get recent messages
    recent_messages = Message.query.order_by(Message.created_at.desc()).limit(10).all()
    
    # Get upcoming maturities (next 30 days)
    upcoming = Investment.query.filter(
        Investment.status == 'active',
        Investment.end_date != None,
        Investment.end_date >= date.today()
    ).order_by(Investment.end_date).limit(5).all()
    
    # Get top rated brokers
    top_brokers = Broker.query.all()
    top_brokers = sorted(top_brokers, key=lambda x: x.average_rating, reverse=True)[:5]
    
    return render_template('dashboard.html',
        total_investments=total_investments,
        total_brokers=total_brokers,
        total_invested_ars=total_invested_ars,
        total_invested_usd=total_invested_usd,
        plazo_fijo_return=plazo_fijo_return,
        recent_messages=recent_messages,
        upcoming=upcoming,
        top_brokers=top_brokers
    )


# ==================== BROKERS ====================

@app.route('/brokers')
@login_required
def brokers_list():
    brokers = Broker.query.order_by(Broker.name).all()
    return render_template('brokers/list.html', brokers=brokers)


@app.route('/brokers/new', methods=['GET', 'POST'])
@login_required
def broker_new():
    if request.method == 'POST':
        broker = Broker(
            name=request.form.get('name'),
            description=request.form.get('description'),
            website=request.form.get('website'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            commission_rate=float(request.form.get('commission_rate') or 0)
        )
        db.session.add(broker)
        db.session.commit()
        flash('Broker creado exitosamente', 'success')
        return redirect(url_for('broker_detail', broker_id=broker.id))
    
    return render_template('brokers/form.html', broker=None)


@app.route('/brokers/<int:broker_id>')
@login_required
def broker_detail(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    user_rating = BrokerRating.query.filter_by(broker_id=broker_id, user_id=current_user.id).first()
    messages = Message.query.filter_by(broker_id=broker_id).order_by(Message.created_at.desc()).all()
    return render_template('brokers/detail.html', broker=broker, user_rating=user_rating, messages=messages)


@app.route('/brokers/<int:broker_id>/edit', methods=['GET', 'POST'])
@login_required
def broker_edit(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    
    if request.method == 'POST':
        broker.name = request.form.get('name')
        broker.description = request.form.get('description')
        broker.website = request.form.get('website')
        broker.phone = request.form.get('phone')
        broker.email = request.form.get('email')
        broker.commission_rate = float(request.form.get('commission_rate') or 0)
        db.session.commit()
        flash('Broker actualizado exitosamente', 'success')
        return redirect(url_for('broker_detail', broker_id=broker.id))
    
    return render_template('brokers/form.html', broker=broker)


@app.route('/brokers/<int:broker_id>/rate', methods=['POST'])
@login_required
def broker_rate(broker_id):
    broker = Broker.query.get_or_404(broker_id)
    category = request.form.get('category', 'general')
    rating_value = int(request.form.get('rating'))
    
    # Find existing rating for this user/broker/category
    rating = BrokerRating.query.filter_by(
        broker_id=broker_id, 
        user_id=current_user.id,
        category=category
    ).first()
    
    if rating:
        rating.rating = rating_value
    else:
        rating = BrokerRating(
            broker_id=broker_id, 
            user_id=current_user.id, 
            category=category,
            rating=rating_value
        )
        db.session.add(rating)
    
    db.session.commit()
    flash(f'Puntuacion de {category} guardada', 'success')
    return redirect(url_for('broker_detail', broker_id=broker_id))


@app.route('/brokers/<int:broker_id>/message', methods=['POST'])
@login_required
def broker_message(broker_id):
    content = request.form.get('content')
    if content:
        message = Message(
            content=content,
            author_id=current_user.id,
            broker_id=broker_id,
            message_type='broker'
        )
        db.session.add(message)
        db.session.commit()
        flash('Mensaje agregado', 'success')
    return redirect(url_for('broker_detail', broker_id=broker_id))


# ==================== INVESTMENTS ====================

@app.route('/investments')
@login_required
def investments_list():
    investment_type = request.args.get('type', 'all')
    status = request.args.get('status', 'active')
    
    query = Investment.query
    
    if investment_type != 'all':
        query = query.filter_by(investment_type=investment_type)
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    investments = query.order_by(Investment.created_at.desc()).all()
    return render_template('investments/list.html', investments=investments, 
                         current_type=investment_type, current_status=status)


@app.route('/investments/new', methods=['GET', 'POST'])
@login_required
def investment_new():
    if request.method == 'POST':
        start_date = None
        end_date = None
        
        if request.form.get('start_date'):
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        if request.form.get('end_date'):
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        
        investment = Investment(
            name=request.form.get('name'),
            investment_type=request.form.get('investment_type'),
            amount=float(request.form.get('amount')),
            currency=request.form.get('currency'),
            interest_rate=float(request.form.get('interest_rate') or 0),
            start_date=start_date,
            end_date=end_date,
            broker_id=request.form.get('broker_id') or None,
            creator_id=current_user.id,
            notes=request.form.get('notes')
        )
        db.session.add(investment)
        db.session.commit()
        flash('Inversión creada exitosamente', 'success')
        return redirect(url_for('investment_detail', investment_id=investment.id))
    
    brokers = Broker.query.order_by(Broker.name).all()
    return render_template('investments/form.html', investment=None, brokers=brokers)


@app.route('/investments/<int:investment_id>')
@login_required
def investment_detail(investment_id):
    investment = Investment.query.get_or_404(investment_id)
    messages = Message.query.filter_by(investment_id=investment_id).order_by(Message.created_at.desc()).all()
    return render_template('investments/detail.html', investment=investment, messages=messages)


@app.route('/investments/<int:investment_id>/edit', methods=['GET', 'POST'])
@login_required
def investment_edit(investment_id):
    investment = Investment.query.get_or_404(investment_id)
    
    if request.method == 'POST':
        investment.name = request.form.get('name')
        investment.investment_type = request.form.get('investment_type')
        investment.amount = float(request.form.get('amount'))
        investment.currency = request.form.get('currency')
        investment.interest_rate = float(request.form.get('interest_rate') or 0)
        investment.status = request.form.get('status')
        investment.notes = request.form.get('notes')
        
        if request.form.get('start_date'):
            investment.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        if request.form.get('end_date'):
            investment.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        if request.form.get('broker_id'):
            investment.broker_id = request.form.get('broker_id')
        
        db.session.commit()
        flash('Inversión actualizada exitosamente', 'success')
        return redirect(url_for('investment_detail', investment_id=investment.id))
    
    brokers = Broker.query.order_by(Broker.name).all()
    return render_template('investments/form.html', investment=investment, brokers=brokers)


@app.route('/investments/<int:investment_id>/message', methods=['POST'])
@login_required
def investment_message(investment_id):
    content = request.form.get('content')
    if content:
        message = Message(
            content=content,
            author_id=current_user.id,
            investment_id=investment_id,
            message_type='investment'
        )
        db.session.add(message)
        db.session.commit()
        flash('Mensaje agregado', 'success')
    return redirect(url_for('investment_detail', investment_id=investment_id))


# ==================== PORTFOLIOS ====================

@app.route('/portfolios')
@login_required
def portfolios_list():
    portfolios = Portfolio.query.order_by(Portfolio.name).all()
    return render_template('portfolios/list.html', portfolios=portfolios)


@app.route('/portfolios/new', methods=['GET', 'POST'])
@login_required
def portfolio_new():
    if request.method == 'POST':
        portfolio = Portfolio(
            name=request.form.get('name'),
            broker_id=request.form.get('broker_id'),
            description=request.form.get('description')
        )
        db.session.add(portfolio)
        db.session.commit()
        flash('Cartera creada exitosamente', 'success')
        return redirect(url_for('portfolio_detail', portfolio_id=portfolio.id))
    
    brokers = Broker.query.order_by(Broker.name).all()
    return render_template('portfolios/form.html', portfolio=None, brokers=brokers)


@app.route('/portfolios/<int:portfolio_id>')
@login_required
def portfolio_detail(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    stocks = Stock.query.order_by(Stock.symbol).all()
    messages = Message.query.filter_by(portfolio_id=portfolio_id).order_by(Message.created_at.desc()).all()
    return render_template('portfolios/detail.html', portfolio=portfolio, stocks=stocks, messages=messages)


@app.route('/portfolios/<int:portfolio_id>/add-stock', methods=['POST'])
@login_required
def portfolio_add_stock(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    
    quantity = float(request.form.get('quantity'))
    purchase_price = float(request.form.get('purchase_price'))
    
    stock_id = request.form.get('stock_id')
    
    # Check if using existing stock or creating new one
    if stock_id and stock_id != 'new':
        # Use existing stock
        stock = Stock.query.get_or_404(int(stock_id))
    else:
        # Create new stock from symbol
        symbol = request.form.get('symbol', '').upper()
        if not symbol:
            flash('Debe ingresar un símbolo para el nuevo activo', 'error')
            return redirect(url_for('portfolio_detail', portfolio_id=portfolio_id))
        
        # Check if stock already exists
        stock = Stock.query.filter_by(symbol=symbol).first()
        if not stock:
            stock = Stock(
                symbol=symbol,
                name=request.form.get('name') or symbol,
                stock_type=request.form.get('stock_type', 'accion'),
                market=request.form.get('market', 'BCBA')
            )
            db.session.add(stock)
            db.session.commit()
    
    # Add to portfolio
    portfolio_stock = PortfolioStock(
        portfolio_id=portfolio_id,
        stock_id=stock.id,
        quantity=quantity,
        purchase_price=purchase_price,
        purchase_date=date.today()
    )
    db.session.add(portfolio_stock)
    db.session.commit()
    
    flash(f'{stock.symbol} agregado a la cartera', 'success')
    return redirect(url_for('portfolio_detail', portfolio_id=portfolio_id))


@app.route('/portfolios/<int:portfolio_id>/message', methods=['POST'])
@login_required
def portfolio_add_message(portfolio_id):
    content = request.form.get('content')
    if content:
        message = Message(
            content=content,
            author_id=current_user.id,
            portfolio_id=portfolio_id,
            message_type='portfolio'
        )
        db.session.add(message)
        db.session.commit()
        flash('Mensaje agregado', 'success')
    return redirect(url_for('portfolio_detail', portfolio_id=portfolio_id))


# ==================== STOCKS ====================

@app.route('/stocks')
@login_required
def stocks_list():
    stocks = Stock.query.order_by(Stock.symbol).all()
    return render_template('stocks/list.html', stocks=stocks)


@app.route('/stocks/add', methods=['POST'])
@login_required
def stocks_add_custom():
    """Add a custom stock/bond by symbol"""
    symbol = request.form.get('symbol', '').upper().strip()
    name = request.form.get('name', '').strip() or symbol
    stock_type = request.form.get('stock_type', 'bono')
    
    if not symbol:
        flash('El simbolo es requerido', 'error')
        return redirect(url_for('stocks_list'))
    
    # Check if already exists
    existing = Stock.query.filter_by(symbol=symbol).first()
    if existing:
        flash(f'{symbol} ya existe', 'warning')
        return redirect(url_for('stocks_list'))
    
    # Create new stock
    stock = Stock(
        symbol=symbol,
        name=name,
        stock_type=stock_type,
        market='BCBA',
        currency='ARS'
    )
    db.session.add(stock)
    db.session.commit()
    
    # Try to get price from IOL
    from iol_service import iol_service
    price_data = iol_service.get_bond_price(symbol)
    
    if price_data and price_data.get('price'):
        stock.current_price = float(price_data['price'])
        stock.last_updated = datetime.utcnow()
        
        # Save to history
        history = PriceHistory(stock_id=stock.id, price=stock.current_price, date=date.today())
        db.session.add(history)
        db.session.commit()
        
        flash(f'{symbol} agregado con precio ${price_data["price"]:,.2f}', 'success')
    else:
        flash(f'{symbol} agregado (sin precio disponible)', 'success')
    
    return redirect(url_for('stocks_list'))


@app.route('/stocks/<int:stock_id>/delete', methods=['POST'])
@login_required
def stock_delete(stock_id):
    """Delete a stock and its history"""
    stock = Stock.query.get_or_404(stock_id)
    symbol = stock.symbol
    
    # Delete price history first
    PriceHistory.query.filter_by(stock_id=stock_id).delete()
    
    # Delete portfolio associations
    PortfolioStock.query.filter_by(stock_id=stock_id).delete()
    
    # Delete the stock
    db.session.delete(stock)
    db.session.commit()
    
    flash(f'{symbol} eliminado', 'success')
    return redirect(url_for('stocks_list'))


@app.route('/stocks/<int:stock_id>/update-price', methods=['POST'])
@login_required
def stock_update_price(stock_id):
    stock = Stock.query.get_or_404(stock_id)
    new_price = float(request.form.get('price'))
    
    stock.current_price = new_price
    stock.last_updated = datetime.utcnow()
    
    # Save to history
    existing_history = PriceHistory.query.filter_by(stock_id=stock_id, date=date.today()).first()
    if existing_history:
        existing_history.price = new_price
    else:
        history = PriceHistory(stock_id=stock_id, price=new_price, date=date.today())
        db.session.add(history)
    
    db.session.commit()
    flash(f'Precio de {stock.symbol} actualizado', 'success')
    return redirect(request.referrer or url_for('stocks_list'))


# ==================== IOL API INTEGRATION ====================

@app.route('/stocks/update-from-iol', methods=['POST'])
@login_required
def stocks_update_from_iol():
    """Update all stock prices from IOL API"""
    from iol_service import iol_service, DEFAULT_BONDS
    
    updated = 0
    errors = []
    
    # Get all stocks in the system
    stocks = Stock.query.all()
    symbols_to_update = [s.symbol for s in stocks] if stocks else DEFAULT_BONDS
    
    # If no stocks exist, create the default bonds
    if not stocks:
        for symbol in DEFAULT_BONDS:
            stock = Stock(
                symbol=symbol,
                name=symbol,
                stock_type='bono',
                market='BCBA',
                currency='ARS'
            )
            db.session.add(stock)
        db.session.commit()
        stocks = Stock.query.all()
        symbols_to_update = [s.symbol for s in stocks]
    
    # Fetch prices from IOL
    prices = iol_service.get_multiple_prices(symbols_to_update)
    
    for symbol, price_data in prices.items():
        stock = Stock.query.filter_by(symbol=symbol).first()
        if stock and price_data.get('price'):
            stock.current_price = float(price_data['price'])
            stock.last_updated = datetime.utcnow()
            
            # Save to history
            existing_history = PriceHistory.query.filter_by(stock_id=stock.id, date=date.today()).first()
            if existing_history:
                existing_history.price = stock.current_price
            else:
                history = PriceHistory(stock_id=stock.id, price=stock.current_price, date=date.today())
                db.session.add(history)
            
            updated += 1
        elif price_data.get('error'):
            errors.append(f"{symbol}: {price_data.get('error')}")
    
    db.session.commit()
    
    if updated > 0:
        flash(f'{updated} precios actualizados desde IOL', 'success')
    if errors:
        flash(f'Errores: {", ".join(errors[:3])}', 'warning')
    
    return redirect(url_for('stocks_list'))


@app.route('/stocks/init-default-bonds', methods=['POST'])
@login_required
def stocks_init_default_bonds():
    """Initialize default Argentine bonds"""
    from iol_service import DEFAULT_BONDS
    
    created = 0
    for symbol in DEFAULT_BONDS:
        existing = Stock.query.filter_by(symbol=symbol).first()
        if not existing:
            stock = Stock(
                symbol=symbol,
                name=symbol,
                stock_type='bono',
                market='BCBA',
                currency='ARS'
            )
            db.session.add(stock)
            created += 1
    
    db.session.commit()
    flash(f'{created} bonos agregados', 'success')
    return redirect(url_for('stocks_list'))


@app.route('/api/iol/test-connection')
@login_required
def api_iol_test_connection():
    """Test IOL API connection"""
    from iol_service import iol_service
    
    if iol_service.authenticate():
        return jsonify({
            'status': 'success',
            'message': 'Conexión exitosa con IOL API',
            'token_expiry': iol_service.token_expiry.isoformat() if iol_service.token_expiry else None
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Error al conectar con IOL API. Verifica las credenciales en .env'
        }), 401


@app.route('/api/iol/price/<symbol>')
@login_required
def api_iol_get_price(symbol):
    """Get price for a specific symbol from IOL"""
    from iol_service import iol_service
    
    price_data = iol_service.get_bond_price(symbol.upper())
    
    if price_data and price_data.get('price'):
        return jsonify(price_data)
    else:
        return jsonify({
            'symbol': symbol,
            'error': 'No se pudo obtener el precio'
        }), 404


@app.route('/stocks/<int:stock_id>/history')
@login_required
def stock_history(stock_id):
    """View price history for a specific stock"""
    stock = Stock.query.get_or_404(stock_id)
    history = PriceHistory.query.filter_by(stock_id=stock_id).order_by(PriceHistory.date.desc()).limit(90).all()
    return render_template('stocks/history.html', stock=stock, history=history)


@app.route('/api/stocks/price-history')
@login_required
def api_stocks_price_history():
    """Get price history for all stocks (last 30 days) for chart"""
    from datetime import timedelta
    
    result = {}
    stocks = Stock.query.all()
    
    for stock in stocks:
        history = PriceHistory.query.filter_by(stock_id=stock.id)\
            .filter(PriceHistory.date >= date.today() - timedelta(days=30))\
            .order_by(PriceHistory.date.asc()).all()
        
        if history:
            result[stock.symbol] = [
                {'date': h.date.strftime('%d/%m'), 'price': h.price}
                for h in history
            ]
    
    return jsonify(result)


@app.route('/api/portfolio/<int:portfolio_id>/value-history')
@login_required
def api_portfolio_value_history(portfolio_id):
    """Get portfolio value history for charts with extended metrics"""
    from datetime import timedelta
    
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    
    # Calculate basic metrics first (these don't depend on history)
    portfolio_stocks = portfolio.stocks.all()
    initial_investment = sum(ps.quantity * ps.purchase_price for ps in portfolio_stocks)
    current_value = portfolio.total_value
    
    gain_loss = current_value - initial_investment
    gain_loss_pct = ((current_value - initial_investment) / initial_investment * 100) if initial_investment > 0 else 0
    
    # Get dates range from portfolio creation date
    end_date = date.today()
    # Use portfolio creation date as start, or 90 days ago if created_at is None
    if portfolio.created_at:
        start_date = portfolio.created_at.date() if hasattr(portfolio.created_at, 'date') else portfolio.created_at
    else:
        start_date = end_date - timedelta(days=90)
    
    # Get all stock IDs in portfolio
    stock_ids = [ps.stock_id for ps in portfolio_stocks]
    stock_quantities = {ps.stock_id: ps.quantity for ps in portfolio_stocks}
    
    # Fetch all price history in one query
    price_history = PriceHistory.query.filter(
        PriceHistory.stock_id.in_(stock_ids),
        PriceHistory.date >= start_date,
        PriceHistory.date <= end_date
    ).all()
    
    # Group prices by date
    prices_by_date = {}
    for ph in price_history:
        if ph.date not in prices_by_date:
            prices_by_date[ph.date] = {}
        prices_by_date[ph.date][ph.stock_id] = ph.price
    
    # Calculate portfolio value for each date
    dates = []
    values = []
    
    for check_date in sorted(prices_by_date.keys()):
        day_prices = prices_by_date[check_date]
        total_value = sum(
            stock_quantities.get(stock_id, 0) * price 
            for stock_id, price in day_prices.items()
        )
        if total_value > 0:
            dates.append(check_date.strftime('%d/%m'))
            values.append(round(total_value, 2))
    
    # If no historical data, add at least today with current value
    if not values and current_value > 0:
        dates.append(date.today().strftime('%d/%m'))
        values.append(round(current_value, 2))
    
    # Calculate max/min from history, or use current if no history
    max_value = max(values) if values else current_value
    min_value = min(values) if values else current_value
    
    return jsonify({
        'portfolio': portfolio.name,
        'dates': dates,
        'values': values,
        'metrics': {
            'initial_investment': round(initial_investment, 2),
            'current_value': round(current_value, 2),
            'gain_loss': round(gain_loss, 2),
            'gain_loss_pct': round(gain_loss_pct, 2),
            'max_value': round(max_value, 2),
            'min_value': round(min_value, 2)
        }
    })


# ==================== API ENDPOINTS ====================

@app.route('/api/dashboard-stats')
@login_required
def api_dashboard_stats():
    investments = Investment.query.filter_by(status='active').all()
    
    # Group by type
    by_type = {}
    for inv in investments:
        if inv.investment_type not in by_type:
            by_type[inv.investment_type] = {'count': 0, 'total_ars': 0, 'total_usd': 0}
        by_type[inv.investment_type]['count'] += 1
        if inv.currency == 'ARS':
            by_type[inv.investment_type]['total_ars'] += inv.amount
        else:
            by_type[inv.investment_type]['total_usd'] += inv.amount
    
    return jsonify(by_type)


@app.route('/api/portfolio-performance/<int:portfolio_id>')
@login_required
def api_portfolio_performance(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    
    performance = []
    for ps in portfolio.stocks.all():
        performance.append({
            'symbol': ps.stock.symbol,
            'quantity': ps.quantity,
            'purchase_price': ps.purchase_price,
            'current_price': ps.stock.current_price,
            'gain_loss': ps.gain_loss,
            'gain_loss_pct': ps.gain_loss_percentage
        })
    
    return jsonify(performance)


# ==================== INIT DB ====================

def init_db():
    with app.app_context():
        db.create_all()
        
        # Create admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@cajaabogados.com',
                full_name='Administrador',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: admin / admin123")


# Start scheduler for production (Gunicorn/Docker)
# This runs when the module is imported
import os
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':  # Avoid double-start in Flask debug mode
    scheduler.start()
    print("[SCHEDULER] Iniciado - Precios se actualizaran cada 30 minutos")


if __name__ == '__main__':
    init_db()
    
    # Run initial price update
    update_prices_from_iol()
    
    app.run(debug=True, port=5000, use_reloader=False)
