"""
PDF 报告生成服务
生成专业的策略回测报告
"""
import io
import base64
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

from src.utils.data_validation import normalize_backtest_results

logger = logging.getLogger(__name__)

# 尝试导入 PDF 库
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not available, PDF generation will use fallback mode")


class PDFGenerator:
    """
    PDF 报告生成器
    """
    
    def __init__(self):
        self.styles = None
        if REPORTLAB_AVAILABLE:
            self._setup_styles()

    def _resolve_metrics(self, backtest_result: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a normalized metric dictionary from supported result shapes."""
        normalized = normalize_backtest_results(backtest_result)
        metrics = normalized.get("metrics", {})

        if not metrics and "performance_metrics" in normalized:
            metrics = normalized.get("performance_metrics", {})
        elif not metrics:
            metrics = normalized

        return metrics

    def _resolve_trades(self, backtest_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Resolve normalized trades for table rendering."""
        normalized = normalize_backtest_results(backtest_result)
        trades = normalized.get("trades", [])
        return trades if isinstance(trades, list) else []
    
    def _setup_styles(self):
        """设置样式"""
        self.styles = getSampleStyleSheet()

        def add_style_if_missing(style):
            if style.name not in self.styles.byName:
                self.styles.add(style)
        
        # 标题样式
        add_style_if_missing(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1e3a5f')
        ))
        
        # 小节标题
        add_style_if_missing(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#2563eb')
        ))
        
        # 正文
        add_style_if_missing(ParagraphStyle(
            name='BodyText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6
        ))
        
        # 指标值
        add_style_if_missing(ParagraphStyle(
            name='MetricValue',
            parent=self.styles['Normal'],
            fontSize=12,
            alignment=TA_RIGHT
        ))
    
    def generate_backtest_report(
        self,
        backtest_result: Dict[str, Any],
        symbol: str,
        strategy: str,
        parameters: Dict = None
    ) -> bytes:
        """
        生成回测报告 PDF
        
        Args:
            backtest_result: 回测结果
            symbol: 股票代码
            strategy: 策略名称
            parameters: 策略参数
            
        Returns:
            PDF 文件的字节内容
        """
        if not REPORTLAB_AVAILABLE:
            return self._generate_fallback_report(backtest_result, symbol, strategy)
        
        try:
            metrics = self._resolve_metrics(backtest_result)
            trades = self._resolve_trades(backtest_result)
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            story = []
            
            # 标题
            story.append(Paragraph("策略回测报告", self.styles['ReportTitle']))
            story.append(Paragraph(
                f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                self.styles['BodyText']
            ))
            story.append(Spacer(1, 20))
            
            # 基本信息
            story.append(Paragraph("基本信息", self.styles['SectionTitle']))
            info_data = [
                ['股票代码', symbol],
                ['交易策略', strategy],
                ['回测周期', f"{backtest_result.get('start_date', 'N/A')} ~ {backtest_result.get('end_date', 'N/A')}"]
            ]
            if parameters:
                for key, value in parameters.items():
                    info_data.append([key, str(value)])
            
            info_table = Table(info_data, colWidths=[150, 250])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e293b')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0'))
            ]))
            story.append(info_table)
            story.append(Spacer(1, 20))
            
            # 核心指标
            story.append(Paragraph("核心指标", self.styles['SectionTitle']))
                
            metrics_data = [
                ['指标', '数值'],
                ['总收益率', f"{metrics.get('total_return', 0) * 100:.2f}%"],
                ['年化收益率', f"{metrics.get('annualized_return', 0) * 100:.2f}%"],
                ['夏普比率', f"{metrics.get('sharpe_ratio', 0):.3f}"],
                ['最大回撤', f"{metrics.get('max_drawdown', 0) * 100:.2f}%"],
                ['胜率', f"{metrics.get('win_rate', 0) * 100:.2f}%"],
                ['总交易次数', str(metrics.get('num_trades', metrics.get('total_trades', 0)))],
                ['初始资金', f"${metrics.get('initial_capital', 0):,.2f}"],
                ['最终价值', f"${metrics.get('final_value', 0):,.2f}"]
            ]
            
            metrics_table = Table(metrics_data, colWidths=[200, 200])
            metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1e293b')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white])
            ]))
            story.append(metrics_table)
            story.append(Spacer(1, 20))
            
            # 风险分析
            if 'risk_metrics' in backtest_result or 'volatility' in metrics:
                story.append(Paragraph("风险分析", self.styles['SectionTitle']))
                risk_data = [
                    ['风险指标', '数值'],
                    ['波动率', f"{metrics.get('volatility', 0) * 100:.2f}%"],
                    ['VaR (95%)', f"{metrics.get('var_95', 0) * 100:.2f}%"],
                    ['CVaR (95%)', f"{metrics.get('cvar_95', 0) * 100:.2f}%"],
                    ['收益标准差', f"{metrics.get('return_std', 0) * 100:.2f}%"]
                ]
                
                risk_table = Table(risk_data, colWidths=[200, 200])
                risk_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fef2f2')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1e293b')),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('PADDING', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#fecaca'))
                ]))
                story.append(risk_table)
                story.append(Spacer(1, 20))
            
            # 交易统计
            if trades:
                story.append(Paragraph("最近交易记录 (最多10条)", self.styles['SectionTitle']))
                
                trade_headers = ['日期', '操作', '价格', '数量', '金额']
                trade_data = [trade_headers]
                
                for trade in trades[-10:]:
                    trade_data.append([
                        str(trade.get('date', 'N/A'))[:10],
                        '买入' if trade.get('action') == 'buy' else '卖出',
                        f"${trade.get('price', 0):.2f}",
                        str(trade.get('quantity', trade.get('shares', 0))),
                        f"${trade.get('value', 0):,.2f}"
                    ])
                
                trade_table = Table(trade_data, colWidths=[80, 60, 80, 60, 100])
                trade_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('PADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1fae5'))
                ]))
                story.append(trade_table)
            
            # 页脚
            story.append(Spacer(1, 40))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0')))
            story.append(Paragraph(
                "本报告由量化交易系统自动生成，仅供参考，不构成投资建议。",
                ParagraphStyle(
                    'Footer',
                    parent=self.styles['Normal'],
                    fontSize=8,
                    textColor=colors.HexColor('#94a3b8'),
                    alignment=TA_CENTER,
                    spaceBefore=10
                )
            ))
            
            doc.build(story)
            pdf_content = buffer.getvalue()
            buffer.close()
            
            return pdf_content
            
        except Exception as e:
            logger.error(f"Error generating PDF report: {e}")
            return self._generate_fallback_report(backtest_result, symbol, strategy)
    
    def _generate_fallback_report(
        self,
        backtest_result: Dict,
        symbol: str,
        strategy: str
    ) -> bytes:
        """生成简单文本报告作为后备"""
        metrics = self._resolve_metrics(backtest_result)
            
        report = f"""
========================================
        策略回测报告
========================================
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

基本信息
--------
股票代码: {symbol}
交易策略: {strategy}

核心指标
--------
总收益率: {metrics.get('total_return', 0) * 100:.2f}%
年化收益率: {metrics.get('annualized_return', 0) * 100:.2f}%
夏普比率: {metrics.get('sharpe_ratio', 0):.3f}
最大回撤: {metrics.get('max_drawdown', 0) * 100:.2f}%
胜率: {metrics.get('win_rate', 0) * 100:.2f}%
总交易次数: {metrics.get('num_trades', metrics.get('total_trades', 0))}
初始资金: ${metrics.get('initial_capital', 0):,.2f}
最终价值: ${metrics.get('final_value', 0):,.2f}

========================================
本报告由量化交易系统自动生成
========================================
"""
        return report.encode('utf-8')
    
    def get_report_base64(
        self,
        backtest_result: Dict,
        symbol: str,
        strategy: str,
        parameters: Dict = None
    ) -> str:
        """生成 Base64 编码的 PDF"""
        pdf_bytes = self.generate_backtest_report(
            backtest_result, symbol, strategy, parameters
        )
        return base64.b64encode(pdf_bytes).decode('utf-8')


# 全局实例
pdf_generator = PDFGenerator()
