// Project-wide UI defaults for the strategy / backtest / trading forms.
//
// The project is a CN A-stock quant tool, so the default symbol is the
// most-recognizable A-share (贵州茅台, 600519.SS) rather than a US ticker.
// Use the Yahoo-compatible suffix so default backtest / analysis calls
// work without relying on backend symbol normalization. Bilingual
// placeholder hints elsewhere still mention `AAPL` so the tool stays
// approachable for non-CN users.
//
// `getCurrencySymbol` returns `¥` for CN-style codes and `$` for US
// tickers, so cash / market-value / target-price renders match the
// underlying market without us having to plumb a currency through every
// component.

export const DEFAULT_SYMBOL = '600519.SS';

// Bilingual placeholder used by code-entry inputs so both A-share and
// US-ticker users see a familiar example.
export const SYMBOL_PLACEHOLDER_BILINGUAL = '600519.SS / AAPL';

const CN_PURE_NUMERIC = /^\d{6}$/; // 600519 / 000858 / 300750 / 512400
const CN_WITH_SUFFIX = /^\d{6}\.(SS|SZ|BJ)$/i; // 600519.SS

// Detect whether a symbol should render with a CNY (¥) prefix.
// Returns true for CN A-share codes; false for US tickers and crypto.
// Treat falsy / unknown values as US-style ($) so legacy callers
// without a symbol keep their previous behavior.
export const isCnSymbol = (symbol) => {
  if (!symbol || typeof symbol !== 'string') {
    return false;
  }
  const trimmed = symbol.trim();
  return CN_PURE_NUMERIC.test(trimmed) || CN_WITH_SUFFIX.test(trimmed);
};

// Pick the currency symbol that matches the trading venue of `symbol`.
// CN A-shares → ¥, everything else → $.
export const getCurrencySymbol = (symbol) => (isCnSymbol(symbol) ? '¥' : '$');

// Human-readable currency name, used in run-summary copy.
export const getCurrencyName = (symbol) => (isCnSymbol(symbol) ? '人民币' : '美元');
