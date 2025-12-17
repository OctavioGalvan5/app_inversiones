from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Relationships
    ratings = db.relationship('BrokerRating', backref='user', lazy='dynamic')
    messages = db.relationship('Message', backref='author', lazy='dynamic')
    investments = db.relationship('Investment', backref='creator', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Broker(db.Model):
    __tablename__ = 'brokers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    website = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    logo_url = db.Column(db.String(300))
    commission_rate = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    ratings = db.relationship('BrokerRating', backref='broker', lazy='dynamic')
    portfolios = db.relationship('Portfolio', backref='broker', lazy='dynamic')
    messages = db.relationship('Message', backref='broker', lazy='dynamic', foreign_keys='Message.broker_id')
    
    # Rating categories
    RATING_CATEGORIES = [
        ('atencion', 'Atencion al Cliente'),
        ('comisiones', 'Comisiones'),
        ('plataforma', 'Plataforma/App'),
        ('velocidad', 'Velocidad de Ejecucion'),
        ('variedad', 'Variedad de Instrumentos'),
        ('general', 'General')
    ]
    
    @property
    def average_rating(self):
        """Overall average across all categories"""
        ratings = self.ratings.all()
        if not ratings:
            return 0
        return sum(r.rating for r in ratings) / len(ratings)
    
    @property
    def rating_count(self):
        """Total number of ratings"""
        return self.ratings.count()
    
    def get_category_average(self, category):
        """Get average rating for a specific category"""
        ratings = self.ratings.filter_by(category=category).all()
        if not ratings:
            return 0
        return sum(r.rating for r in ratings) / len(ratings)
    
    def get_category_count(self, category):
        """Get number of ratings for a specific category"""
        return self.ratings.filter_by(category=category).count()
    
    def get_all_category_ratings(self):
        """Get ratings grouped by category"""
        result = {}
        for cat_id, cat_name in self.RATING_CATEGORIES:
            avg = self.get_category_average(cat_id)
            count = self.get_category_count(cat_id)
            result[cat_id] = {
                'name': cat_name,
                'average': avg,
                'count': count
            }
        return result
    
    def get_user_ratings(self, user_id):
        """Get all ratings from a specific user for this broker"""
        return {r.category: r.rating for r in self.ratings.filter_by(user_id=user_id).all()}
    
    def __repr__(self):
        return f'<Broker {self.name}>'


class BrokerRating(db.Model):
    __tablename__ = 'broker_ratings'
    
    id = db.Column(db.Integer, primary_key=True)
    broker_id = db.Column(db.Integer, db.ForeignKey('brokers.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(50), default='general')  # Category of rating
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('broker_id', 'user_id', 'category', name='unique_broker_user_category_rating'),
    )


class Investment(db.Model):
    __tablename__ = 'investments'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    investment_type = db.Column(db.String(50), nullable=False)  # 'plazo_fijo', 'bono', 'accion', 'fci', 'crypto'
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='ARS')  # ARS, USD
    interest_rate = db.Column(db.Float)  # For plazo fijo
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='active')  # active, completed, cancelled
    broker_id = db.Column(db.Integer, db.ForeignKey('brokers.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    broker_rel = db.relationship('Broker', backref='investments')
    messages = db.relationship('Message', backref='investment', lazy='dynamic', foreign_keys='Message.investment_id')
    
    @property
    def calculated_return(self):
        """Calculate expected return for plazo fijo"""
        if self.investment_type == 'plazo_fijo' and self.interest_rate and self.start_date and self.end_date:
            days = (self.end_date - self.start_date).days
            return self.amount * (self.interest_rate / 100) * (days / 365)
        return 0
    
    @property
    def total_at_maturity(self):
        """Total amount at maturity"""
        return self.amount + self.calculated_return
    
    def __repr__(self):
        return f'<Investment {self.name}>'


class Portfolio(db.Model):
    __tablename__ = 'portfolios'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    broker_id = db.Column(db.Integer, db.ForeignKey('brokers.id'), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    stocks = db.relationship('PortfolioStock', backref='portfolio', lazy='dynamic')
    
    @property
    def total_value(self):
        return sum(ps.current_value for ps in self.stocks.all())
    
    def __repr__(self):
        return f'<Portfolio {self.name}>'


class Stock(db.Model):
    __tablename__ = 'stocks'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)  # GGAL, YPFD, AAPL
    name = db.Column(db.String(150))
    stock_type = db.Column(db.String(20), default='accion')  # accion, bono, cedear
    market = db.Column(db.String(20), default='BCBA')  # BCBA, NYSE, NASDAQ
    current_price = db.Column(db.Float, default=0)
    currency = db.Column(db.String(10), default='ARS')
    last_updated = db.Column(db.DateTime)
    
    # Relationships
    price_history = db.relationship('PriceHistory', backref='stock', lazy='dynamic')
    portfolio_stocks = db.relationship('PortfolioStock', backref='stock', lazy='dynamic')
    
    def __repr__(self):
        return f'<Stock {self.symbol}>'


class PortfolioStock(db.Model):
    __tablename__ = 'portfolio_stocks'
    
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolios.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stocks.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    
    @property
    def current_value(self):
        return self.quantity * self.stock.current_price if self.stock.current_price else 0
    
    @property
    def gain_loss(self):
        return self.current_value - (self.quantity * self.purchase_price)
    
    @property
    def gain_loss_percentage(self):
        cost = self.quantity * self.purchase_price
        if cost == 0:
            return 0
        return ((self.current_value - cost) / cost) * 100


class PriceHistory(db.Model):
    __tablename__ = 'price_history'
    
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stocks.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    volume = db.Column(db.BigInteger)
    date = db.Column(db.Date, nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('stock_id', 'date', name='unique_stock_date'),
    )


class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    broker_id = db.Column(db.Integer, db.ForeignKey('brokers.id'))
    investment_id = db.Column(db.Integer, db.ForeignKey('investments.id'))
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolios.id'))
    message_type = db.Column(db.String(20), default='general')  # general, broker, investment, portfolio
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    portfolio = db.relationship('Portfolio', backref='messages')
    
    def __repr__(self):
        return f'<Message {self.id}>'
