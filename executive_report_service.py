# -*- coding: utf-8 -*-
"""
Executive Report Service - Generates comprehensive PDF reports for investment decisions
Includes portfolio analysis, broker ratings, investment summaries, and charts
"""

from io import BytesIO
from datetime import datetime, date
import json
import pytz

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm, inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, KeepTogether, HRFlowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker

from models import db, Broker, Portfolio, PortfolioStock, Investment, Stock, PriceHistory
from datetime import timedelta

# Argentina timezone
BUENOS_AIRES_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

# Professional color scheme
COLORS = {
    'primary': colors.HexColor('#1a365d'),      # Dark navy
    'secondary': colors.HexColor('#2c5282'),    # Medium blue
    'accent': colors.HexColor('#3182ce'),       # Bright blue
    'success': colors.HexColor('#38a169'),      # Green
    'danger': colors.HexColor('#e53e3e'),       # Red
    'warning': colors.HexColor('#d69e2e'),      # Yellow
    'text_dark': colors.HexColor('#1a202c'),
    'text_muted': colors.HexColor('#718096'),
    'bg_light': colors.HexColor('#f7fafc'),
    'border': colors.HexColor('#e2e8f0'),
    'gold': colors.HexColor('#ecc94b'),
}

# Chart colors for pie charts
CHART_COLORS = [
    colors.HexColor('#3182ce'),  # Blue
    colors.HexColor('#38a169'),  # Green
    colors.HexColor('#d69e2e'),  # Yellow
    colors.HexColor('#e53e3e'),  # Red
    colors.HexColor('#805ad5'),  # Purple
    colors.HexColor('#dd6b20'),  # Orange
    colors.HexColor('#319795'),  # Teal
    colors.HexColor('#d53f8c'),  # Pink
]


def to_buenos_aires(dt):
    """Convert a datetime to Buenos Aires timezone"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(BUENOS_AIRES_TZ)


def format_currency(amount, currency='ARS'):
    """Format amount as currency"""
    if amount is None:
        return '-'
    symbol = '$' if currency == 'ARS' else 'US$'
    return f"{symbol} {amount:,.2f}"


def format_percentage(value):
    """Format value as percentage"""
    if value is None:
        return '-'
    sign = '+' if value > 0 else ''
    return f"{sign}{value:.2f}%"


def get_detailed_broker_data():
    """Get detailed data for each broker including portfolios and investments"""
    brokers = Broker.query.all()
    broker_list = []
    
    for broker in brokers:
        broker_data = {
            'id': broker.id,
            'name': broker.name,
            'description': broker.description,
            'average_rating': broker.average_rating,
            'rating_count': broker.rating_count,
            'category_ratings': broker.get_all_category_ratings(),
            'portfolios': [],
            'investments': [],
            'total_invested': 0,
            'total_current': 0,
            'total_gain_loss': 0,
            'by_stock_type': {}
        }
        
        # Get portfolios
        for portfolio in broker.portfolios.all():
            portfolio_data = {
                'id': portfolio.id,
                'name': portfolio.name,
                'invested': 0,
                'current': 0,
                'gain_loss': 0,
                'gain_loss_pct': 0,
                'stocks': [],
                'by_type': {}
            }
            
            for ps in portfolio.stocks.all():
                invested = ps.quantity * ps.purchase_price
                current = ps.current_value
                gain_loss = ps.gain_loss
                
                portfolio_data['invested'] += invested
                portfolio_data['current'] += current
                portfolio_data['gain_loss'] += gain_loss
                
                stock_type = ps.stock.stock_type or 'otro'
                if stock_type not in portfolio_data['by_type']:
                    portfolio_data['by_type'][stock_type] = {'invested': 0, 'current': 0}
                portfolio_data['by_type'][stock_type]['invested'] += invested
                portfolio_data['by_type'][stock_type]['current'] += current
                
                if stock_type not in broker_data['by_stock_type']:
                    broker_data['by_stock_type'][stock_type] = {'invested': 0, 'current': 0}
                broker_data['by_stock_type'][stock_type]['invested'] += invested
                broker_data['by_stock_type'][stock_type]['current'] += current
                
                portfolio_data['stocks'].append({
                    'symbol': ps.stock.symbol,
                    'name': ps.stock.name,
                    'type': stock_type,
                    'quantity': ps.quantity,
                    'purchase_price': ps.purchase_price,
                    'current_price': ps.stock.current_price,
                    'invested': invested,
                    'current': current,
                    'gain_loss': gain_loss,
                    'gain_loss_pct': ps.gain_loss_percentage
                })
            
            if portfolio_data['invested'] > 0:
                portfolio_data['gain_loss_pct'] = (portfolio_data['gain_loss'] / portfolio_data['invested']) * 100
            
            broker_data['total_invested'] += portfolio_data['invested']
            broker_data['total_current'] += portfolio_data['current']
            broker_data['total_gain_loss'] += portfolio_data['gain_loss']
            
            broker_data['portfolios'].append(portfolio_data)
        
        # Get investments - investments maintain their value until maturity
        for inv in broker.investments:
            if inv.status == 'active':
                broker_data['investments'].append({
                    'id': inv.id,
                    'name': inv.name,
                    'type': inv.investment_type,
                    'amount': inv.amount,
                    'currency': inv.currency,
                    'interest_rate': inv.interest_rate,
                    'start_date': inv.start_date,
                    'end_date': inv.end_date,
                    'calculated_return': inv.calculated_return,
                    'total_at_maturity': inv.total_at_maturity
                })
                # Investments maintain their nominal value (no gain/loss until maturity)
                broker_data['total_invested'] += inv.amount
                broker_data['total_current'] += inv.amount  # Value stays the same
        
        broker_list.append(broker_data)
    
    return sorted(broker_list, key=lambda x: x['total_invested'], reverse=True)


def create_pie_chart(data, labels, width=180, height=130):
    """Create a pie chart drawing with percentages in legend"""
    if not data or sum(data) == 0:
        return None
    
    total = sum(data)
    drawing = Drawing(width, height)
    
    pie = Pie()
    pie.x = 30
    pie.y = 15
    pie.width = 70
    pie.height = 70
    pie.data = data
    pie.labels = None
    
    for i, color in enumerate(CHART_COLORS[:len(data)]):
        pie.slices[i].fillColor = color
        pie.slices[i].strokeColor = colors.white
        pie.slices[i].strokeWidth = 1
    
    drawing.add(pie)
    
    # Legend with percentages
    legend = Legend()
    legend.x = 110
    legend.y = height - 25
    legend.dx = 8
    legend.dy = 8
    legend.fontName = 'Helvetica'
    legend.fontSize = 7
    legend.boxAnchor = 'nw'
    legend.columnMaximum = 6
    legend.strokeWidth = 0
    legend.deltay = 10
    legend.dxTextSpace = 4
    
    # Add percentage to labels
    labels_with_pct = []
    for i in range(len(labels)):
        pct = (data[i] / total * 100) if total > 0 else 0
        labels_with_pct.append(f"{labels[i]} ({pct:.1f}%)")
    
    legend.colorNamePairs = [(CHART_COLORS[i], labels_with_pct[i]) for i in range(len(labels))]
    drawing.add(legend)
    
    return drawing


def get_portfolio_value_history(portfolio_id, days=30):
    """Get historical portfolio values for the last N days"""
    portfolio = Portfolio.query.get(portfolio_id)
    if not portfolio:
        return [], []
    
    portfolio_stocks = portfolio.stocks.all()
    if not portfolio_stocks:
        return [], []
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    stock_ids = [ps.stock_id for ps in portfolio_stocks]
    stock_quantities = {ps.stock_id: ps.quantity for ps in portfolio_stocks}
    
    # Fetch price history
    price_history = PriceHistory.query.filter(
        PriceHistory.stock_id.in_(stock_ids),
        PriceHistory.date >= start_date,
        PriceHistory.date <= end_date
    ).all()
    
    # Group by date
    prices_by_date = {}
    for ph in price_history:
        if ph.date not in prices_by_date:
            prices_by_date[ph.date] = {}
        prices_by_date[ph.date][ph.stock_id] = ph.price
    
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
    
    return dates, values


def create_line_chart(dates, values, width=280, height=70):
    """Create a cleaner line chart for portfolio evolution"""
    if not dates or not values or len(values) < 2:
        return None
    
    drawing = Drawing(width, height)
    
    # Create line plot
    lp = LinePlot()
    lp.x = 50
    lp.y = 18
    lp.width = width - 65
    lp.height = height - 30
    
    # Convert values to the format LinePlot expects
    data_points = [(i, values[i]) for i in range(len(values))]
    lp.data = [data_points]
    
    # Styling
    is_positive = values[-1] >= values[0]
    line_color = COLORS['success'] if is_positive else COLORS['danger']
    
    lp.lines[0].strokeColor = line_color
    lp.lines[0].strokeWidth = 1.5
    lp.lines[0].symbol = None
    
    # Y Axis - better formatting for large numbers
    lp.yValueAxis.strokeColor = COLORS['border']
    lp.yValueAxis.labels.fontName = 'Helvetica'
    lp.yValueAxis.labels.fontSize = 6
    lp.yValueAxis.gridStrokeColor = COLORS['border']
    lp.yValueAxis.gridStrokeWidth = 0.3
    lp.yValueAxis.visibleGrid = True
    
    # Format Y axis labels properly for millions
    def format_value(x):
        if x >= 1000000:
            return f'${x/1000000:.1f}M'
        elif x >= 1000:
            return f'${x/1000:.0f}K'
        else:
            return f'${x:.0f}'
    
    lp.yValueAxis.labelTextFormat = format_value
    
    # X Axis
    lp.xValueAxis.visible = False
    
    drawing.add(lp)
    
    # Add date labels at bottom
    if len(dates) >= 2:
        drawing.add(String(50, 5, dates[0], fontName='Helvetica', fontSize=6, fillColor=COLORS['text_muted']))
        drawing.add(String(width - 15, 5, dates[-1], fontName='Helvetica', fontSize=6, fillColor=COLORS['text_muted'], textAnchor='end'))
    
    # Add value change indicator
    change = values[-1] - values[0]
    change_pct = (change / values[0] * 100) if values[0] > 0 else 0
    change_text = f"{'↑' if change >= 0 else '↓'} {format_value(abs(change))} ({change_pct:+.1f}%)"
    change_color = COLORS['success'] if change >= 0 else COLORS['danger']
    drawing.add(String(width - 15, height - 8, change_text, fontName='Helvetica-Bold', fontSize=7, fillColor=change_color, textAnchor='end'))
    
    return drawing


def create_rating_bars(category_ratings, width=250, height=100):
    """Create horizontal bar chart for category ratings"""
    drawing = Drawing(width, height)
    
    categories = []
    values = []
    
    for cat_id, cat_data in category_ratings.items():
        if cat_data['average'] > 0:
            categories.append(cat_data['name'][:12])
            values.append(cat_data['average'])
    
    if not values:
        return None
    
    # Draw bars manually for better control
    bar_height = 12
    bar_spacing = 16
    max_bar_width = 100
    start_x = 100
    start_y = height - 20
    
    for i, (cat, val) in enumerate(zip(categories, values)):
        y_pos = start_y - (i * bar_spacing)
        bar_width = (val / 5.0) * max_bar_width
        
        # Category label
        drawing.add(String(start_x - 5, y_pos + 2, cat, fontName='Helvetica', fontSize=7, textAnchor='end'))
        
        # Background bar
        drawing.add(Rect(start_x, y_pos, max_bar_width, bar_height, fillColor=COLORS['bg_light'], strokeColor=None))
        
        # Value bar
        bar_color = COLORS['success'] if val >= 4 else (COLORS['warning'] if val >= 3 else COLORS['danger'])
        drawing.add(Rect(start_x, y_pos, bar_width, bar_height, fillColor=bar_color, strokeColor=None))
        
        # Stars
        stars = '★' * int(val) + '☆' * (5 - int(val))
        drawing.add(String(start_x + max_bar_width + 5, y_pos + 2, f"{val:.1f}", fontName='Helvetica', fontSize=7))
    
    return drawing


def generate_executive_report_pdf():
    """
    Generate comprehensive Executive Investment Report PDF organized by Broker
    
    Returns:
        BytesIO buffer containing the PDF
    """
    from functools import partial
    
    buffer = BytesIO()
    
    # Get all data organized by broker
    brokers_data = get_detailed_broker_data()
    
    # Calculate totals
    total_invested = sum(b['total_invested'] for b in brokers_data)
    total_current = sum(b['total_current'] for b in brokers_data)
    total_gain_loss = sum(b['total_gain_loss'] for b in brokers_data)
    total_portfolios = sum(len(b['portfolios']) for b in brokers_data)
    total_investments = sum(len(b['investments']) for b in brokers_data)
    
    def add_page_header_footer(canvas, doc):
        """Add header and footer to each page"""
        canvas.saveState()
        width, height = A4
        
        # Header
        canvas.setFillColor(COLORS['primary'])
        canvas.rect(0, height - 50, width, 50, fill=True, stroke=False)
        
        canvas.setFillColor(COLORS['accent'])
        canvas.rect(0, height - 54, width, 4, fill=True, stroke=False)
        
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 16)
        canvas.drawString(30, height - 35, "Reporte Ejecutivo de Inversiones")
        
        now_ar = to_buenos_aires(datetime.utcnow())
        canvas.setFont('Helvetica', 9)
        canvas.drawRightString(width - 30, height - 30, f"Generado: {now_ar.strftime('%d/%m/%Y %H:%M')} hs")
        canvas.drawRightString(width - 30, height - 42, "Hora Argentina")
        
        # Footer
        canvas.setStrokeColor(COLORS['border'])
        canvas.setLineWidth(1)
        canvas.line(30, 30, width - 30, 30)
        
        canvas.setFillColor(COLORS['text_muted'])
        canvas.setFont('Helvetica', 8)
        canvas.drawCentredString(width / 2, 15, f"Página {canvas.getPageNumber()}")
        canvas.drawString(30, 15, "Confidencial - Solo para uso interno")
        canvas.drawRightString(width - 30, 15, now_ar.strftime('%d/%m/%Y'))
        
        canvas.restoreState()
    
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=70,
        bottomMargin=50
    )
    
    styles = getSampleStyleSheet()
    elements = []
    
    # Styles
    section_title = ParagraphStyle('SectionTitle', parent=styles['Heading1'], fontSize=14, textColor=COLORS['primary'], spaceAfter=12, spaceBefore=15)
    subsection_title = ParagraphStyle('Subsection', parent=styles['Heading2'], fontSize=11, textColor=COLORS['secondary'], spaceAfter=8, spaceBefore=10)
    broker_title = ParagraphStyle('BrokerTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.white, spaceAfter=5, spaceBefore=0)
    normal_style = ParagraphStyle('NormalText', parent=styles['Normal'], fontSize=9, textColor=COLORS['text_dark'], spaceAfter=4)
    small_style = ParagraphStyle('SmallText', parent=styles['Normal'], fontSize=8, textColor=COLORS['text_muted'], spaceAfter=3)
    
    # ==================== RESUMEN EJECUTIVO ====================
    elements.append(Paragraph("Resumen Ejecutivo", section_title))
    
    # Stats cards
    total_gain_pct = (total_gain_loss / total_invested * 100) if total_invested > 0 else 0
    
    stats_data = [
        ['BROKERS', 'CARTERAS', 'INVERSIONES', 'TOTAL INVERTIDO', 'VALOR ACTUAL'],
        [str(len(brokers_data)), str(total_portfolios), str(total_investments), 
         format_currency(total_invested), format_currency(total_current)]
    ]
    
    stats_table = Table(stats_data, colWidths=[2.4*cm, 2.4*cm, 2.5*cm, 4*cm, 4*cm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLORS['primary']),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('TEXTCOLOR', (0, 1), (-1, -1), COLORS['text_dark']),
        ('BACKGROUND', (0, 1), (-1, -1), COLORS['bg_light']),
        ('BOX', (0, 0), (-1, -1), 1, COLORS['border']),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 10))
    
    # Performance
    perf_color = COLORS['success'] if total_gain_loss >= 0 else COLORS['danger']
    perf_text = f"{'↑ Ganancia' if total_gain_loss >= 0 else '↓ Pérdida'}: {format_currency(abs(total_gain_loss))} ({total_gain_pct:+.2f}%)"
    perf_style = ParagraphStyle('Perf', parent=styles['Normal'], fontSize=13, textColor=perf_color, fontName='Helvetica-Bold')
    elements.append(Paragraph(perf_text, perf_style))
    elements.append(Spacer(1, 12))
    
    # Two charts side by side: Distribution by Broker + Distribution by Asset Type
    all_stock_types = {}
    for broker in brokers_data:
        for stock_type, data in broker['by_stock_type'].items():
            if stock_type not in all_stock_types:
                all_stock_types[stock_type] = 0
            all_stock_types[stock_type] += data['current']
    
    type_translations = {'accion': 'Acciones', 'bono': 'Bonos', 'cedear': 'CEDEARs', 'otro': 'Otros'}
    
    charts_data = []
    
    # Broker distribution chart
    if len(brokers_data) > 0 and total_invested > 0:
        broker_labels = [b['name'][:12] for b in brokers_data if b['total_invested'] > 0]
        broker_values = [b['total_invested'] for b in brokers_data if b['total_invested'] > 0]
        
        if broker_values:
            broker_chart = create_pie_chart(broker_values, broker_labels, 200, 100)
            if broker_chart:
                charts_data.append(('Distribución por Broker', broker_chart))
    
    # Asset type distribution chart
    if all_stock_types and sum(all_stock_types.values()) > 0:
        type_labels = [type_translations.get(t, t.title()) for t in all_stock_types.keys() if all_stock_types[t] > 0]
        type_values = [v for v in all_stock_types.values() if v > 0]
        
        if type_values:
            type_chart = create_pie_chart(type_values, type_labels, 200, 100)
            if type_chart:
                charts_data.append(('Distribución por Tipo de Activo', type_chart))
    
    if charts_data:
        if len(charts_data) == 2:
            chart_table = Table([
                [Paragraph(charts_data[0][0], small_style), Paragraph(charts_data[1][0], small_style)],
                [charts_data[0][1], charts_data[1][1]]
            ], colWidths=[8*cm, 8*cm])
        else:
            chart_table = Table([
                [Paragraph(charts_data[0][0], small_style)],
                [charts_data[0][1]]
            ], colWidths=[16*cm])
        
        chart_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(chart_table)
        elements.append(Spacer(1, 15))
    
    # Top Performing Portfolios Table
    all_portfolios = []
    for broker in brokers_data:
        for portfolio in broker['portfolios']:
            all_portfolios.append({
                'name': portfolio['name'],
                'broker': broker['name'],
                'invested': portfolio['invested'],
                'current': portfolio['current'],
                'gain_loss': portfolio['gain_loss'],
                'gain_loss_pct': portfolio['gain_loss_pct']
            })
    
    if all_portfolios:
        elements.append(Paragraph("Top Carteras por Rendimiento", subsection_title))
        
        sorted_portfolios = sorted(all_portfolios, key=lambda x: x['gain_loss_pct'], reverse=True)
        
        port_table_data = [['CARTERA', 'BROKER', 'INVERTIDO', 'ACTUAL', 'RESULTADO']]
        for p in sorted_portfolios[:5]:  # Top 5
            result_text = f"{format_currency(p['gain_loss'])} ({p['gain_loss_pct']:+.1f}%)"
            port_table_data.append([
                p['name'][:18],
                p['broker'][:12],
                format_currency(p['invested']),
                format_currency(p['current']),
                result_text
            ])
        
        port_table = Table(port_table_data, colWidths=[3.5*cm, 2.5*cm, 3*cm, 3*cm, 4*cm])
        port_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS['secondary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLORS['bg_light']]),
            ('BOX', (0, 0), (-1, -1), 0.5, COLORS['border']),
            ('LINEBELOW', (0, 0), (-1, 0), 1, COLORS['accent']),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(port_table)
        elements.append(Spacer(1, 15))
    
    # Broker comparison table
    if brokers_data:
        elements.append(Paragraph("Comparación de Brokers", subsection_title))
        
        broker_comp_data = [['BROKER', 'CALIFICACIÓN', 'INVERTIDO', 'VALOR ACTUAL', 'RENDIMIENTO']]
        for b in brokers_data:
            b_gain = b['total_current'] - b['total_invested'] if b['total_invested'] > 0 else 0
            b_gain_pct = (b_gain / b['total_invested'] * 100) if b['total_invested'] > 0 else 0
            stars = '★' * int(b['average_rating']) + '☆' * (5 - int(b['average_rating']))
            
            broker_comp_data.append([
                b['name'][:15],
                f"{stars} ({b['average_rating']:.1f})",
                format_currency(b['total_invested']),
                format_currency(b['total_current']),
                f"{format_currency(b_gain)} ({b_gain_pct:+.1f}%)"
            ])
        
        broker_comp_table = Table(broker_comp_data, colWidths=[3*cm, 3*cm, 3*cm, 3*cm, 4*cm])
        broker_comp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS['primary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLORS['bg_light']]),
            ('BOX', (0, 0), (-1, -1), 0.5, COLORS['border']),
            ('LINEBELOW', (0, 0), (-1, 0), 1, COLORS['accent']),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(broker_comp_table)
    
    # ==================== SECCIONES POR BROKER ====================
    for broker_idx, broker in enumerate(brokers_data):
        elements.append(PageBreak())
        
        # Broker Header with gradient-like effect
        broker_header_data = [[
            Paragraph(f"🏢 {broker['name']}", broker_title),
            Paragraph(f"{'★' * int(broker['average_rating'])}{'☆' * (5 - int(broker['average_rating']))} ({broker['average_rating']:.1f})", 
                     ParagraphStyle('Rating', parent=styles['Normal'], fontSize=14, textColor=COLORS['gold']))
        ]]
        
        broker_header = Table(broker_header_data, colWidths=[10*cm, 5*cm])
        broker_header.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), COLORS['primary']),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('RIGHTPADDING', (1, 0), (1, 0), 15),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(broker_header)
        elements.append(Spacer(1, 10))
        
        # Broker summary stats
        broker_gain_pct = (broker['total_gain_loss'] / broker['total_invested'] * 100) if broker['total_invested'] > 0 else 0
        
        summary_data = [
            ['TOTAL INVERTIDO', 'VALOR ACTUAL', 'RESULTADO', 'CARTERAS', 'INVERSIONES'],
            [
                format_currency(broker['total_invested']),
                format_currency(broker['total_current']),
                f"{format_currency(broker['total_gain_loss'])} ({broker_gain_pct:+.1f}%)",
                str(len(broker['portfolios'])),
                str(len(broker['investments']))
            ]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*cm, 3*cm, 4*cm, 2*cm, 2.5*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS['secondary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BACKGROUND', (0, 1), (-1, -1), COLORS['bg_light']),
            ('BOX', (0, 0), (-1, -1), 1, COLORS['border']),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 15))
        
        # Two columns: Rating bars + Distribution pie
        col_data = []
        
        # Rating bars
        rating_chart = create_rating_bars(broker['category_ratings'], 220, 90)
        
        # Distribution by stock type
        type_labels = []
        type_values = []
        type_translations = {'accion': 'Acciones', 'bono': 'Bonos', 'cedear': 'CEDEARs', 'otro': 'Otros'}
        for stock_type, data in broker['by_stock_type'].items():
            if data['current'] > 0:
                type_labels.append(type_translations.get(stock_type, stock_type.title()))
                type_values.append(data['current'])
        
        pie_chart = create_pie_chart(type_values, type_labels, 180, 100) if type_values else None
        
        if rating_chart or pie_chart:
            charts_row = []
            if rating_chart:
                charts_row.append([Paragraph("Calificación por Categoría", small_style), rating_chart])
            if pie_chart:
                charts_row.append([Paragraph("Distribución por Tipo", small_style), pie_chart])
            
            if len(charts_row) == 2:
                charts_table = Table([[charts_row[0][0], charts_row[1][0]], [charts_row[0][1], charts_row[1][1]]], colWidths=[8*cm, 7*cm])
            elif len(charts_row) == 1:
                charts_table = Table([[charts_row[0][0]], [charts_row[0][1]]], colWidths=[15*cm])
            
            charts_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ]))
            elements.append(charts_table)
            elements.append(Spacer(1, 10))
        
        # PORTFOLIOS
        if broker['portfolios']:
            elements.append(Paragraph("📊 Carteras", subsection_title))
            
            for portfolio in broker['portfolios']:
                gain_color = COLORS['success'] if portfolio['gain_loss'] >= 0 else COLORS['danger']
                
                port_header = ParagraphStyle('PortHeader', parent=styles['Normal'], fontSize=10, textColor=COLORS['secondary'], fontName='Helvetica-Bold')
                elements.append(Paragraph(f"{portfolio['name']}", port_header))
                
                port_summary = f"Invertido: {format_currency(portfolio['invested'])} → Actual: {format_currency(portfolio['current'])}"
                elements.append(Paragraph(port_summary, small_style))
                
                gain_style = ParagraphStyle('Gain', parent=styles['Normal'], fontSize=9, textColor=gain_color, fontName='Helvetica-Bold')
                gain_text = f"{'Ganancia' if portfolio['gain_loss'] >= 0 else 'Pérdida'}: {format_currency(abs(portfolio['gain_loss']))} ({portfolio['gain_loss_pct']:+.2f}%)"
                elements.append(Paragraph(gain_text, gain_style))
                
                # Stocks table
                if portfolio['stocks']:
                    stock_data = [['Activo', 'Tipo', 'Cant.', 'P.Compra', 'P.Actual', 'Resultado']]
                    
                    for stock in sorted(portfolio['stocks'], key=lambda x: x['current'], reverse=True)[:8]:
                        result_text = f"{format_currency(stock['gain_loss'])} ({stock['gain_loss_pct']:+.1f}%)"
                        stock_data.append([
                            stock['symbol'],
                            stock['type'].upper()[:4],
                            f"{stock['quantity']:,.0f}",
                            format_currency(stock['purchase_price']),
                            format_currency(stock['current_price']),
                            result_text
                        ])
                    
                    stock_table = Table(stock_data, colWidths=[2.2*cm, 1.3*cm, 1.8*cm, 2.5*cm, 2.5*cm, 4*cm])
                    stock_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), COLORS['bg_light']),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 7),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 7),
                        ('ALIGN', (2, 0), (4, -1), 'RIGHT'),
                        ('BOX', (0, 0), (-1, -1), 0.5, COLORS['border']),
                        ('LINEBELOW', (0, 0), (-1, 0), 1, COLORS['accent']),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLORS['bg_light']]),
                    ]))
                    elements.append(stock_table)
                    
                    # Create side-by-side charts: Distribution + Evolution
                    chart_elements = []
                    
                    # Portfolio distribution chart - by individual asset
                    port_pie = None
                    if len(portfolio['stocks']) > 1:
                        asset_labels = []
                        asset_values = []
                        for stock in sorted(portfolio['stocks'], key=lambda x: x['current'], reverse=True)[:6]:
                            if stock['current'] > 0:
                                asset_labels.append(stock['symbol'])
                                asset_values.append(stock['current'])
                        
                        if len(asset_values) > 1:
                            port_pie = create_pie_chart(asset_values, asset_labels, 180, 75)
                    
                    # Evolution chart - portfolio value history (last 30 days)
                    line_chart = None
                    hist_dates, hist_values = get_portfolio_value_history(portfolio['id'], days=30)
                    if len(hist_values) >= 2:
                        line_chart = create_line_chart(hist_dates, hist_values, 220, 65)
                    
                    # Display charts side-by-side if both exist
                    if port_pie and line_chart:
                        elements.append(Spacer(1, 5))
                        charts_table = Table([
                            [Paragraph("Distribución:", small_style), Paragraph("Evolución (30 días):", small_style)],
                            [port_pie, line_chart]
                        ], colWidths=[7*cm, 8*cm])
                        charts_table.setStyle(TableStyle([
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ]))
                        elements.append(charts_table)
                    elif port_pie:
                        elements.append(Spacer(1, 5))
                        elements.append(Paragraph("Distribución:", small_style))
                        elements.append(port_pie)
                    elif line_chart:
                        elements.append(Spacer(1, 5))
                        elements.append(Paragraph("Evolución (30 días):", small_style))
                        elements.append(line_chart)
                
                elements.append(Spacer(1, 10))
        
        # INVESTMENTS
        if broker['investments']:
            elements.append(Paragraph("💰 Inversiones", subsection_title))
            
            type_translations = {'plazo_fijo': 'Plazo Fijo', 'bono': 'Bono', 'fci': 'FCI', 'crypto': 'Cripto', 'accion': 'Acción'}
            
            inv_data = [['Nombre', 'Tipo', 'Capital', 'Tasa', 'Vencimiento', 'Total Esperado']]
            
            for inv in broker['investments']:
                end_date = inv['end_date'].strftime('%d/%m/%Y') if inv['end_date'] else '-'
                rate = f"{inv['interest_rate']:.1f}%" if inv['interest_rate'] else '-'
                
                inv_data.append([
                    inv['name'][:20],
                    type_translations.get(inv['type'], inv['type']),
                    format_currency(inv['amount'], inv['currency']),
                    rate,
                    end_date,
                    format_currency(inv['total_at_maturity'], inv['currency'])
                ])
            
            inv_table = Table(inv_data, colWidths=[3.5*cm, 2*cm, 2.8*cm, 1.5*cm, 2.2*cm, 2.8*cm])
            inv_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), COLORS['bg_light']),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
                ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                ('BOX', (0, 0), (-1, -1), 0.5, COLORS['border']),
                ('LINEBELOW', (0, 0), (-1, 0), 1, COLORS['accent']),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLORS['bg_light']]),
            ]))
            elements.append(inv_table)
    
    # Build PDF
    doc.build(
        elements,
        onFirstPage=add_page_header_footer,
        onLaterPages=add_page_header_footer
    )
    buffer.seek(0)
    return buffer
