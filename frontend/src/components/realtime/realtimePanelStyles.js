// Realtime panel styles extracted verbatim from RealTimePanel.jsx so the host
// component focuses on hook orchestration and layout. The exported string is
// rendered through the same inline <style>{REALTIME_PANEL_STYLES}</style> element,
// preserving the identical CSS text and DOM output.
const REALTIME_PANEL_STYLES = `
        .realtime-panel-shell {
          padding: 0;
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          align-content: start;
          gap: 18px;
          background:
            radial-gradient(circle at top left, color-mix(in srgb, var(--accent-primary) 10%, transparent 90%), transparent 34%),
            radial-gradient(circle at top right, color-mix(in srgb, var(--accent-secondary) 12%, transparent 88%), transparent 30%);
        }

        .realtime-panel-shell > * {
          min-width: 0;
        }

        .realtime-panel-shell .app-page-section-block {
          min-width: 0;
        }

        .realtime-hero {
          display: grid;
          grid-template-columns: minmax(0, 1.42fr) minmax(420px, 0.9fr);
          gap: 12px;
          padding: 12px 14px;
          background:
            linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 12%, var(--bg-secondary) 88%) 0%, color-mix(in srgb, var(--accent-secondary) 10%, var(--bg-secondary) 90%) 100%);
        }

        .realtime-hero__main,
        .realtime-hero__sidecar {
          min-width: 0;
        }

        .realtime-hero__main {
          display: grid;
          gap: 10px;
          align-content: start;
        }

        .realtime-hero__statusbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          flex-wrap: wrap;
        }

        .realtime-hero__eyebrow {
          font-size: 11px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--text-secondary);
          font-weight: 700;
        }

        .realtime-hero__status-meta {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 10px;
          flex-wrap: wrap;
        }

        .realtime-hero__title-row {
          display: flex;
          align-items: flex-start;
          justify-content: flex-start;
          gap: 12px;
        }

        .realtime-hero__headline {
          min-width: 0;
        }

        .realtime-hero__subtitle {
          margin-top: 6px;
          max-width: 560px;
          color: var(--text-secondary);
          line-height: 1.55;
          font-size: 12px;
        }

        .realtime-hero__meta {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .realtime-hero__chip {
          padding: 6px 10px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, var(--border-color) 84%);
          font-size: 11px;
          color: var(--text-secondary);
          white-space: nowrap;
        }

        .realtime-hero__focus-pill {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 8px 12px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-secondary) 84%, white 16%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 18%, var(--border-color) 82%);
          min-width: 0;
          max-width: min(100%, 420px);
        }

        .realtime-hero__focus-label {
          font-size: 10px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
          white-space: nowrap;
        }

        .realtime-hero__focus-text {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .realtime-hero__metric-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
        }

        .realtime-hero__metric {
          padding: 9px 10px;
          border-radius: 8px;
          background: color-mix(in srgb, var(--bg-secondary) 88%, white 12%);
          border: 1px solid color-mix(in srgb, var(--border-color) 78%, white 22%);
        }

        .realtime-hero__metric-label {
          font-size: 11px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-hero__metric-value {
          margin-top: 6px;
          font-size: 20px;
          line-height: 1.05;
          font-weight: 800;
          letter-spacing: 0;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .realtime-hero__metric-detail {
          margin-top: 4px;
          font-size: 11px;
          line-height: 1.4;
          color: var(--text-secondary);
        }

        .realtime-hero__telemetry {
          display: flex;
          flex-wrap: wrap;
          gap: 6px 10px;
          color: var(--text-secondary);
          font-size: 11px;
          line-height: 1.5;
        }

        .realtime-hero__telemetry span {
          padding: 4px 0;
          white-space: nowrap;
        }

        .realtime-hero__sidecar {
          display: grid;
          gap: 8px 10px;
          align-content: start;
          padding: 8px;
          border-radius: 8px;
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, var(--border-color) 84%);
        }

        .realtime-hero__sidecar--desktop-toolbar {
          grid-template-columns: minmax(210px, 240px) minmax(0, 1fr);
          grid-template-areas:
            "actions signal"
            "utility signal";
          align-items: start;
        }

        .realtime-hero__action-row {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
          grid-area: actions;
        }

        .realtime-hero__refresh {
          min-height: 38px;
          font-weight: 700;
        }

        .realtime-hero__secondary-button {
          min-height: 36px;
          min-width: 116px;
        }

        .realtime-hero__utility-row {
          display: grid;
          grid-template-columns: 1fr;
          gap: 8px;
          grid-area: utility;
        }

        .realtime-hero__toggle-pill {
          display: inline-flex;
          align-items: center;
          gap: 12px;
          padding: 8px 10px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-primary) 92%, white 8%);
          border: 1px solid var(--border-color);
        }

        .realtime-hero__utility-actions {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          align-items: stretch;
          justify-content: stretch;
          gap: 8px;
        }

        .realtime-hero__signal-stack {
          display: grid;
          gap: 8px;
          grid-area: signal;
          align-self: stretch;
        }

        .realtime-hero__signal-card {
          padding: 9px 10px;
          border-radius: 8px;
        }

        .realtime-hero__signal-card-title {
          font-weight: 700;
          font-size: 13px;
          line-height: 1.4;
        }

        .realtime-hero__signal-pill-row {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
        }

        .realtime-hero__signal-pill {
          display: inline-flex;
          align-items: center;
          padding: 4px 8px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-primary) 86%, white 14%);
          border: 1px solid color-mix(in srgb, var(--border-color) 76%, white 24%);
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }

        .realtime-hero__signal-pill--accent {
          background: color-mix(in srgb, var(--accent-primary) 16%, var(--bg-primary) 84%);
          border-color: color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%);
        }

        .realtime-hero__signal-card-detail {
          margin-top: 4px;
          font-size: 12px;
          line-height: 1.45;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .realtime-hero__signal-card-detail--muted {
          font-size: 11px;
          color: var(--text-secondary);
        }

        .realtime-overview-grid {
          display: grid;
          grid-template-columns: minmax(360px, 1.2fr) minmax(300px, 0.9fr);
          gap: 18px;
        }

        .realtime-search-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 14px;
          margin-top: 16px;
        }

        .realtime-search-panel {
          padding: 16px;
          border-radius: 18px;
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
          border: 1px solid color-mix(in srgb, var(--border-color) 74%, white 26%);
        }

        .realtime-search-panel__title {
          font-size: 14px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-search-panel__hint {
          margin-top: 6px;
          font-size: 12px;
          line-height: 1.6;
          color: var(--text-secondary);
        }

        .realtime-overview-stats {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
          margin-top: 16px;
        }

        .realtime-overview-stats--compact {
          grid-template-columns: repeat(3, minmax(0, 1fr));
          margin-top: 12px;
        }

        .realtime-overview-brief {
          margin-top: 14px;
          padding: 14px 16px;
          border-radius: 18px;
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
          border: 1px solid color-mix(in srgb, var(--border-color) 76%, white 24%);
        }

        .realtime-overview-brief__label {
          font-size: 11px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-overview-brief__value {
          margin-top: 8px;
          font-size: 24px;
          line-height: 1.1;
          font-weight: 800;
          color: var(--text-primary);
        }

        .realtime-overview-brief__detail {
          margin-top: 8px;
          font-size: 12px;
          line-height: 1.6;
          color: var(--text-secondary);
        }

        .realtime-overview-stat {
          padding: 14px 16px;
          border-radius: 18px;
          border: 1px solid color-mix(in srgb, var(--border-color) 76%, white 24%);
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
        }

        .realtime-overview-stat--primary {
          background: linear-gradient(135deg, rgba(14, 165, 233, 0.14), rgba(56, 189, 248, 0.05));
        }

        .realtime-overview-stat--positive {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.14), rgba(34, 197, 94, 0.05));
        }

        .realtime-overview-stat--negative {
          background: linear-gradient(135deg, rgba(239, 68, 68, 0.14), rgba(239, 68, 68, 0.05));
        }

        .realtime-overview-stat--focus {
          background: linear-gradient(135deg, rgba(168, 85, 247, 0.14), rgba(168, 85, 247, 0.05));
        }

        .realtime-overview-stat--neutral {
          grid-column: 1 / -1;
        }

        .realtime-overview-stat__label {
          font-size: 11px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-overview-stat__value {
          margin-top: 10px;
          font-size: 26px;
          line-height: 1.05;
          font-weight: 800;
          letter-spacing: 0;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .realtime-overview-stat__detail {
          margin-top: 8px;
          font-size: 12px;
          line-height: 1.55;
          color: var(--text-secondary);
        }

        .realtime-block-title {
          font-size: 18px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-block-subtitle {
          margin-top: 6px;
          color: var(--text-secondary);
          font-size: 13px;
          line-height: 1.65;
        }

        .realtime-watch-group-add.ant-btn {
          min-width: 96px;
        }

        .realtime-search-panel .ant-select-customize-input .ant-select-selector {
          height: 40px;
          min-height: 40px;
          overflow: visible;
        }

        .realtime-search-compact .ant-select-auto-complete {
          min-width: 0;
        }

        .realtime-search-compact .ant-btn {
          flex: 0 0 72px;
          min-width: 72px;
          padding-inline: 12px !important;
        }

        .realtime-board-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 18px;
          flex-wrap: wrap;
        }

        .realtime-board-headline {
          display: grid;
          gap: 10px;
          min-width: 0;
        }

        .realtime-board-badges {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }

        .realtime-board-controls {
          display: grid;
          gap: 12px;
          justify-items: end;
          min-width: min(100%, 520px);
        }

        .realtime-board-control-group {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 10px;
          flex-wrap: wrap;
          min-width: 0;
        }

        .realtime-board-control-label {
          font-size: 12px;
          white-space: nowrap;
        }

        .realtime-board-control-group .ant-btn {
          border-radius: 999px;
        }

        .realtime-board-control-group .ant-space {
          display: inline-flex;
          flex-wrap: wrap;
          row-gap: 8px;
        }

        .realtime-board-control-group .ant-space-item {
          margin-inline-end: 0 !important;
        }

        .realtime-board-summary {
          display: inline-flex;
          align-items: baseline;
          gap: 10px;
          padding: 10px 14px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-primary) 88%, white 12%);
          border: 1px solid var(--border-color);
          color: var(--text-secondary);
        }

        .realtime-board-summary strong {
          font-size: 22px;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .market-tabs .ant-tabs-nav {
          margin-bottom: 20px;
        }

        .market-tabs .ant-tabs-tab {
          border-radius: 999px !important;
          padding-inline: 16px !important;
        }

        [data-realtime-board-density='compact'] .realtime-board-head {
          gap: 12px;
          margin-bottom: 14px;
        }

        [data-realtime-board-density='compact'] .realtime-board-headline {
          gap: 8px;
        }

        [data-realtime-board-density='compact'] .realtime-board-badges {
          gap: 8px;
        }

        [data-realtime-board-density='compact'] .realtime-board-summary {
          gap: 8px;
          padding: 8px 12px;
        }

        [data-realtime-board-density='compact'] .realtime-board-summary strong {
          font-size: 18px;
        }

        [data-realtime-board-density='compact'] .realtime-board-controls {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: flex-start;
          gap: 8px 10px;
          min-width: 0;
          width: 100%;
        }

        [data-realtime-board-density='compact'] .realtime-board-control-group {
          justify-content: flex-start;
          gap: 8px;
          padding: 8px 10px;
          border-radius: 18px;
          background: color-mix(in srgb, var(--bg-primary) 90%, white 10%);
          border: 1px solid color-mix(in srgb, var(--border-color) 82%, white 18%);
        }

        [data-realtime-board-density='compact'] .realtime-board-control-group--selection-active {
          flex-basis: 100%;
        }

        [data-realtime-board-density='compact'] .realtime-board-control-label {
          font-size: 11px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }

        [data-realtime-board-density='compact'] .realtime-board-control-group .ant-btn {
          min-height: 30px;
          padding-inline: 12px;
        }

        [data-realtime-board-density='compact'] .market-tabs .ant-tabs-nav {
          margin-bottom: 16px;
        }

        [data-realtime-board-density='compact'] .market-tabs .ant-tabs-tab {
          padding-inline: 14px !important;
        }

        .realtime-quote-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 16px;
          align-items: stretch;
        }

        .realtime-quote-grid--list {
          grid-template-columns: 1fr;
        }

        .realtime-quote-card__surface {
          min-height: 100%;
          display: grid;
          gap: 16px;
        }

        .realtime-quote-card__header,
        .realtime-quote-card__price-row,
        .realtime-quote-card__footer {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }

        .realtime-quote-card__header > :first-child,
        .realtime-quote-card__price-row > :first-child {
          min-width: 0;
          flex: 1 1 auto;
        }

        .realtime-quote-card__tags {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
          flex-wrap: wrap;
        }

        .realtime-quote-card__name {
          margin-bottom: 4px;
        }

        .realtime-quote-card__sparkline {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          max-width: 100%;
          margin-top: 10px;
          padding: 8px 10px;
          border-radius: 14px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--border-color) 78%, white 22%);
          color: var(--text-secondary);
          font-size: 11px;
          line-height: 1.4;
        }

        .realtime-quote-card__sparkline svg {
          display: block;
          flex: none;
        }

        .realtime-quote-card--grid .realtime-quote-card__sparkline svg {
          width: 104px;
          height: 38px;
        }

        .realtime-quote-card__sparkline span {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .realtime-quote-card__source {
          display: grid;
          gap: 4px;
          justify-items: end;
          text-align: right;
          min-width: 0;
          max-width: min(44%, 164px);
          flex: 0 1 164px;
          padding: 10px 12px;
          border-radius: 16px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--border-color) 80%, white 20%);
          color: var(--text-secondary);
        }

        .realtime-quote-card__source-label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          opacity: 0.72;
        }

        .realtime-quote-card__source-value {
          font-size: 13px;
          font-weight: 700;
          line-height: 1.3;
          white-space: normal;
          word-break: break-word;
          overflow-wrap: anywhere;
        }

        .realtime-quote-card__source-detail {
          font-size: 11px;
          line-height: 1.3;
          white-space: normal;
          word-break: break-word;
          overflow-wrap: anywhere;
          opacity: 0.82;
        }

        .realtime-quote-card__price {
          font-size: 32px;
          line-height: 1;
          font-weight: 800;
          color: var(--text-primary);
          letter-spacing: 0;
        }

        .realtime-quote-card__delta {
          margin-top: 8px;
          font-size: 14px;
          font-weight: 700;
        }

        .realtime-quote-card__focus {
          min-width: 120px;
          text-align: right;
          padding: 10px 12px;
          border-radius: 16px;
          background: rgba(15, 23, 42, 0.04);
        }

        .realtime-quote-card__focus-label {
          font-size: 11px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-quote-card__focus-value {
          margin-top: 6px;
          font-size: 13px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-quote-card__metrics {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
        }

        .realtime-quote-card__metric {
          padding: 12px;
          border-radius: 16px;
          background: color-mix(in srgb, var(--bg-secondary) 80%, white 20%);
          border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent 30%);
          display: grid;
          gap: 8px;
        }

        .realtime-quote-card__metric span {
          font-size: 11px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-quote-card__metric strong {
          font-size: 13px;
          line-height: 1.45;
          color: var(--text-primary);
          word-break: break-word;
        }

        .realtime-quote-card__footer {
          align-items: center;
          padding-top: 4px;
        }

        .realtime-quote-card--list .realtime-quote-card__surface--list {
          grid-template-columns: minmax(0, 1.45fr) minmax(180px, 0.7fr) minmax(280px, 0.95fr) auto;
          align-items: center;
        }

        .realtime-quote-card--list .realtime-quote-card__header > :first-child,
        .realtime-quote-card--list .realtime-quote-card__price-row > :first-child {
          min-width: 0;
        }

        .realtime-quote-card--list .realtime-quote-card__header,
        .realtime-quote-card--list .realtime-quote-card__price-row,
        .realtime-quote-card--list .realtime-quote-card__footer {
          align-items: center;
        }

        .realtime-quote-card--list .realtime-quote-card__price-row {
          justify-content: flex-start;
        }

        .realtime-quote-card--list .realtime-quote-card__price {
          font-size: 26px;
        }

        .realtime-quote-card--list .realtime-quote-card__focus {
          min-width: auto;
          text-align: left;
        }

        .realtime-quote-card--list .realtime-quote-card__footer {
          flex-wrap: wrap;
          gap: 12px;
          justify-content: flex-end;
        }

        .realtime-quote-card--list .realtime-quote-card__footer .ant-space,
        .realtime-quote-card--list .realtime-quote-card__footer .ant-space-item {
          flex-wrap: wrap;
        }

        .realtime-quote-card--list.realtime-quote-card--list-split .realtime-quote-card__surface--list {
          grid-template-columns: 1fr 1fr;
        }

        .realtime-quote-card--list.realtime-quote-card--list-stacked .realtime-quote-card__surface--list {
          grid-template-columns: 1fr;
        }

        .realtime-quote-card--list.realtime-quote-card--list-split .realtime-quote-card__footer,
        .realtime-quote-card--list.realtime-quote-card--list-stacked .realtime-quote-card__footer {
          justify-content: flex-start;
        }

        .realtime-quote-card--list.realtime-quote-card--list-stacked .realtime-quote-card__header,
        .realtime-quote-card--list.realtime-quote-card--list-stacked .realtime-quote-card__price-row {
          flex-wrap: wrap;
        }

        @media (max-width: 1320px) {
          .realtime-hero__metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .realtime-overview-stats--compact {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 1180px) {
          .realtime-overview-grid,
          .realtime-hero {
            grid-template-columns: 1fr;
          }

          .realtime-hero__sidecar--desktop-toolbar {
            grid-template-columns: 1fr;
            grid-template-areas:
              "actions"
              "utility"
              "signal";
          }

          .realtime-search-grid,
          .realtime-hero__metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .realtime-board-controls {
            justify-items: start;
            min-width: 100%;
          }

          .realtime-board-control-group {
            justify-content: flex-start;
          }

          .realtime-quote-card--list .realtime-quote-card__surface--list {
            grid-template-columns: 1fr 1fr;
          }

          .realtime-hero__status-meta {
            justify-content: flex-start;
          }
        }

        @media (max-width: 900px) {
          [data-realtime-board-density='compact'] .realtime-board-controls {
            gap: 8px;
          }

          [data-realtime-board-density='compact'] .realtime-board-control-group {
            width: 100%;
          }

          .realtime-overview-stats,
          .realtime-quote-card__metrics {
            grid-template-columns: 1fr 1fr;
          }

          .realtime-overview-stat--neutral {
            grid-column: auto;
          }

          .realtime-quote-card--list .realtime-quote-card__surface--list {
            grid-template-columns: 1fr;
          }

          .realtime-overview-stats--compact {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 640px) {
          .realtime-panel-shell {
            padding: 12px;
          }

          .realtime-hero {
            gap: 8px;
            padding: 10px;
          }

          .realtime-hero__main {
            gap: 8px;
          }

          .realtime-hero__statusbar {
            gap: 6px;
          }

          .realtime-hero__eyebrow {
            font-size: 10px;
            letter-spacing: 0.14em;
          }

          .realtime-hero__headline .ant-typography {
            font-size: 21px !important;
            line-height: 1.16;
          }

          .realtime-hero__subtitle {
            display: none;
          }

          .realtime-hero__title-row,
          .realtime-hero__utility-row,
          .realtime-board-control-group {
            align-items: flex-start;
          }

          .realtime-hero__status-meta,
          .realtime-hero__utility-actions {
            width: 100%;
            justify-content: flex-start;
          }

          .realtime-hero__meta {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            scrollbar-width: none;
          }

          .realtime-hero__chip--category,
          .realtime-hero__chip--auto {
            display: none;
          }

          .realtime-hero__meta::-webkit-scrollbar,
          .realtime-hero__metric-grid::-webkit-scrollbar {
            display: none;
          }

          .realtime-hero__focus-pill,
          .realtime-hero__utility-actions .ant-btn {
            width: 100%;
          }

          .realtime-hero__focus-pill {
            gap: 8px;
            padding: 6px 10px;
          }

          .realtime-hero__focus-label {
            font-size: 9px;
          }

          .realtime-hero__focus-text {
            font-size: 11px;
          }

          .realtime-hero__chip {
            padding: 4px 8px;
            font-size: 10px;
          }

          .realtime-hero__action-row,
          .realtime-hero__utility-actions {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            display: grid;
          }

          .realtime-hero__metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 6px;
          }

          .realtime-hero__metric {
            min-height: 40px;
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            grid-template-areas: "label value";
            align-items: center;
            gap: 8px;
            padding: 7px 8px;
          }

          .realtime-hero__metric-label {
            grid-area: label;
            letter-spacing: 0.08em;
          }

          .realtime-hero__metric-value {
            grid-area: value;
            margin-top: 0;
            font-size: 18px;
            text-align: right;
          }

          .realtime-hero__metric-detail {
            display: none;
          }

          .realtime-hero__sidecar {
            gap: 6px;
            padding: 8px;
          }

          .realtime-hero__utility-row {
            display: grid;
            grid-template-columns: 1fr;
            gap: 8px;
            width: 100%;
          }

          .realtime-hero__toggle-pill {
            width: 100%;
            justify-content: space-between;
            gap: 10px;
            padding: 6px 8px;
          }

          .realtime-hero__toggle-pill .ant-typography {
            white-space: nowrap;
          }

          .realtime-hero__refresh {
            min-height: 34px;
          }

          .realtime-hero__secondary-button,
          .realtime-hero__utility-actions .ant-btn {
            min-height: 32px;
            min-width: 0;
          }

          .realtime-hero__signal-card {
            padding: 7px 8px;
          }

          .realtime-hero__signal-pill {
            padding: 3px 7px;
            font-size: 9px;
          }

          .realtime-hero__utility-actions .ant-btn {
            justify-content: center;
          }

          .realtime-hero__utility-actions .ant-btn > span:not(.anticon) {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }

          .realtime-quote-grid,
          .realtime-overview-stats,
          .realtime-quote-card__metrics {
            grid-template-columns: 1fr;
          }

          .realtime-quote-card__header,
          .realtime-quote-card__price-row,
          .realtime-quote-card__footer {
            flex-direction: column;
            align-items: stretch;
          }

          .realtime-quote-card__source,
          .realtime-quote-card__focus {
            text-align: left;
          }

          .realtime-quote-card__source {
            justify-items: start;
            max-width: none;
          }

          .realtime-hero__telemetry span {
            white-space: normal;
          }

          .realtime-hero__signal-card-detail {
            -webkit-line-clamp: 1;
          }

          .realtime-hero__signal-card-detail--muted {
            display: none;
          }
        }

        @media (max-width: 360px) {
          .realtime-hero__action-row,
          .realtime-hero__utility-actions {
            grid-template-columns: 1fr;
          }
        }
      `;

export default REALTIME_PANEL_STYLES;
