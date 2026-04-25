console.info("%c 合肥水务卡片 \n%c        v1.0 ", "color: #1E88E5; font-weight: bold; background: black", "color: white; font-weight: bold; background: black");
import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";


class HfWaterCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
    };
  }

  static get styles() {
    return css`
      .form {
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding: 16px;
      }
      label {
        font-weight: bold;
        font-size: 14px;
        color: var(--primary-text-color);
      }
      select, input {
        padding: 8px 12px;
        border: 1px solid var(--primary-color);
        border-radius: 4px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        font-size: 14px;
      }
    `;
  }

  render() {
    if (!this.hass) return html``;

    const entities = Object.keys(this.hass.states).filter(
      (e) => {
        const state = this.hass.states[e];
        return e.startsWith("sensor.") && state && state.attributes &&
          state.attributes.sensor_key === "account_balance";
      }
    );

    return html`
      <div class="form">
        <label>实体：
          <select
            @change=${this._valueChanged}
            .value=${this.config.entity || ""}
            name="entity"
          >
            <option value="">-- 选择实体 --</option>
            ${entities.map(
              (e) => html`<option value="${e}" ?selected=${this.config.entity === e}>${e} (${this.hass.states[e].attributes.friendly_name || ""})</option>`
            )}
          </select>
        </label>
        <label>标题：
          <input
            type="text"
            @change=${this._valueChanged}
            .value=${this.config.title || "合肥水务"}
            name="title"
          />
        </label>
      </div>
    `;
  }

  _valueChanged(e) {
    if (!this.config) return;
    const name = e.target.name;
    const value = e.target.value;
    this.config = { ...this.config, [name]: value };
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this.config } }));
  }
}
customElements.define("hfwater-card-editor", HfWaterCardEditor);


class HfWaterCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _showBills: { type: Boolean },
      _showPayRecords: { type: Boolean },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      .card {
        background: var(--card-background-color, #fff);
        border-radius: var(--border-radius, 12px);
        box-shadow: var(--box-shadow, 0 2px 8px rgba(0,0,0,0.1));
        overflow: hidden;
        font-family: var(--primary-font-family, sans-serif);
        color: var(--primary-text-color, #333);
      }
      .card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px 8px;
      }
      .card-title {
        font-size: 18px;
        font-weight: bold;
        color: var(--primary-text-color);
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .card-title img.card-logo {
        width: 28px;
        height: 28px;
        border-radius: 4px;
        object-fit: contain;
      }
      .card-subtitle {
        font-size: 12px;
        color: var(--secondary-text-color, #999);
        margin-top: 2px;
      }

      /* 汇总行 */
      .summary-row {
        display: flex;
        justify-content: space-around;
        padding: 12px 16px;
        gap: 8px;
      }
      .summary-item {
        text-align: center;
        flex: 1;
      }
      .summary-value {
        font-size: 20px;
        font-weight: bold;
        color: var(--primary-text-color);
      }
      .summary-value.blue { color: #1E88E5; }
      .summary-value.green { color: #43A047; }
      .summary-value.orange { color: #FF6D00; }
      .summary-label {
        font-size: 11px;
        color: var(--secondary-text-color, #999);
        margin-top: 2px;
      }

      /* 信息行 */
      .info-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 20px;
        border-top: 1px solid var(--divider-color, #eee);
        font-size: 13px;
      }
      .info-label {
        color: var(--secondary-text-color, #999);
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .info-label ha-icon {
        --mdi-icon-size: 16px;
        color: #1E88E5;
      }
      .info-value {
        color: var(--primary-text-color);
        font-weight: 500;
      }
      .info-value.orange {
        color: #FF6D00;
        font-weight: bold;
      }
      .info-value.blue {
        color: #1E88E5;
        font-weight: bold;
      }

      /* 6期账单表格 */
      .bill-section {
        padding: 4px 16px 16px;
      }
      .bill-title {
        font-size: 13px;
        font-weight: 500;
        color: var(--primary-text-color);
        padding: 8px 4px;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .bill-title ha-icon {
        --mdi-icon-size: 16px;
        color: #1E88E5;
      }
      .bill-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .bill-table th {
        background: #1E88E5;
        color: #fff;
        padding: 8px 6px;
        text-align: center;
        font-weight: 500;
        font-size: 11px;
      }
      .bill-table th:first-child {
        border-radius: 6px 0 0 0;
      }
      .bill-table th:last-child {
        border-radius: 0 6px 0 0;
      }
      .bill-table td {
        padding: 8px 6px;
        text-align: center;
        border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.06));
        color: var(--primary-text-color);
      }
      .bill-table tr:last-child td {
        border-bottom: none;
      }
      .bill-table tr:hover td {
        background: rgba(30, 136, 229, 0.08);
      }
      .bill-usage {
        color: #1E88E5;
        font-weight: 600;
      }
      .bill-fee {
        color: #FF6D00;
        font-weight: 600;
      }
      .bill-period {
        font-weight: 500;
      }

      .no-data {
        text-align: center;
        padding: 40px 20px;
        color: var(--secondary-text-color, #999);
        font-size: 14px;
      }

      /* 展开/收起按钮 */
      .toggle-wrap {
        display: flex;
        justify-content: center;
        gap: 12px;
        padding: 6px 16px 10px;
        border-top: 1px solid var(--divider-color, #eee);
      }
      .toggle-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 16px;
        border-radius: 20px;
        border: 1px solid var(--divider-color, #eee);
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 13px;
        cursor: pointer;
        transition: all 0.2s;
      }
      .toggle-btn:hover {
        background: #1E88E5;
        color: #fff;
        border-color: #1E88E5;
      }
      .toggle-btn.active {
        background: #1E88E5;
        color: #fff;
        border-color: #1E88E5;
      }
      .toggle-btn ha-icon {
        --mdi-icon-size: 16px;
      }
    `;
  }

  constructor() {
    super();
    this._showBills = false;
    this._showPayRecords = false;
  }

  static getConfigElement() {
    return document.createElement("hfwater-card-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:hfwater-card",
      entity: "",
      title: "合肥水务",
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("请指定实体");
    }
    this.config = { title: "合肥水务", ...config };
  }

  getCardSize() {
    return 5;
  }

  get _entityState() {
    if (!this.hass || !this.config) return null;
    return this.hass.states[this.config.entity];
  }

  _fmt(val, decimals = 2) {
    if (val === null || val === undefined || val === "") return "-";
    const n = parseFloat(val);
    return isNaN(n) ? val : n.toFixed(decimals);
  }

  _findEntity(key) {
    if (!this.hass || !this.config) return null;
    const mainEntity = this.hass.states[this.config.entity];
    if (!mainEntity) return null;

    // 从主实体获取 customer_id，通过属性匹配查找目标实体
    const customerId = mainEntity.attributes?.customer_id;
    if (!customerId) return null;

    // 遍历所有实体，匹配 sensor_key + customer_id
    for (const [entityId, entity] of Object.entries(this.hass.states)) {
      if (entity.attributes?.sensor_key === key && entity.attributes?.customer_id === customerId) {
        return entity;
      }
    }

    // Fallback: 通过 entity_id 格式匹配 sensor.hfwater_{customerId}_{key}
    const fallbackId = `sensor.hfwater_${customerId}_${key}`;
    return this.hass.states[fallbackId] || null;
  }

  _getEntityValue(key) {
    const entity = this._findEntity(key);
    if (entity) {
      return entity.state;
    }
    return null;
  }

  _getEntityAttrs(key) {
    const entity = this._findEntity(key);
    if (entity) {
      return entity.attributes || {};
    }
    return {};
  }

  render() {
    const mainEntity = this._entityState;
    if (!mainEntity) {
      return html`
        <ha-card>
          <div class="no-data">未找到实体数据，请先配置集成</div>
        </ha-card>
      `;
    }

    const mainAttrs = mainEntity.attributes || {};
    const customerName = mainAttrs.customer_name || "";
    const customerAddress = mainAttrs.customer_address || "";

    const balance = this._getEntityValue("account_balance");
    const needPay = this._getEntityValue("user_need_pay");
    const billUsage = this._getEntityValue("latest_bill_water_usage");
    const billMeterReading = this._getEntityValue("latest_bill_meter_reading");

    const lateFee = this._getEntityValue("user_late_fee");
    const billAmount = this._getEntityValue("latest_bill_amount");
    const billDate = this._getEntityValue("latest_bill_date");
    const payAmount = this._getEntityValue("latest_pay_amount");

    const billsAttrs = this._getEntityAttrs("recent_bills_total");
    const billlist = billsAttrs["最近6期账单"] || [];

    const payAttrs = this._getEntityAttrs("latest_pay_amount");
    const payRecords = payAttrs["最近缴费记录"] || [];

    return html`
      <ha-card class="card">
        <div class="card-header">
          <div>
            <div class="card-title">
              <img class="card-logo" src="/hfwater-local/logo.png" alt="logo">
              ${this.config.title || "合肥水务"}
            </div>
            ${customerName || customerAddress
              ? html`<div class="card-subtitle">${customerName}${customerName && customerAddress ? " · " : ""}${customerAddress}</div>`
              : ""}
          </div>
        </div>

        <!-- 汇总数据 -->
        <div class="summary-row">
          <div class="summary-item">
            <div class="summary-value green">${this._fmt(balance)}</div>
            <div class="summary-label">账户余额</div>
          </div>
          <div class="summary-item">
            <div class="summary-value orange">${this._fmt(needPay)}</div>
            <div class="summary-label">应缴水费</div>
          </div>
          <div class="summary-item">
            <div class="summary-value blue">${this._fmt(billUsage, 1)}</div>
            <div class="summary-label">出账水量</div>
          </div>
          <div class="summary-item">
            <div class="summary-value" style="color:var(--primary-text-color)">${this._fmt(billMeterReading, 1)}</div>
            <div class="summary-label">出账读数</div>
          </div>
        </div>

        <!-- 详细信息行 -->
        <div class="info-row">
          <span class="info-label">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            违约金
          </span>
          <span class="info-value">${this._fmt(lateFee)} 元</span>
        </div>
        <div class="info-row">
          <span class="info-label">
            <ha-icon icon="mdi:currency-cny"></ha-icon>
            最近出账金额
          </span>
          <span class="info-value">${this._fmt(billAmount)} 元</span>
        </div>
        <div class="info-row">
          <span class="info-label">
            <ha-icon icon="mdi:cash-check"></ha-icon>
            最近缴费金额
          </span>
          <span class="info-value">${this._fmt(payAmount)} 元</span>
        </div>
        <div class="info-row">
          <span class="info-label">
            <ha-icon icon="mdi:calendar"></ha-icon>
            最近出账日期
          </span>
          <span class="info-value">${billDate || "-"}</span>
        </div>

        <!-- 按钮行 -->
        ${(billlist.length > 0 || payRecords.length > 0) ? html`
        <div class="toggle-wrap">
          ${billlist.length > 0 ? html`
          <div class="toggle-btn ${this._showBills ? "active" : ""}" @click=${() => { this._showBills = !this._showBills; }}>
            <ha-icon icon=${this._showBills ? "mdi:chevron-up" : "mdi:chevron-down"}></ha-icon>
            ${this._showBills ? "收起账单" : "最近账单"}
          </div>
          ` : ""}
          ${payRecords.length > 0 ? html`
          <div class="toggle-btn ${this._showPayRecords ? "active" : ""}" @click=${() => { this._showPayRecords = !this._showPayRecords; }}>
            <ha-icon icon=${this._showPayRecords ? "mdi:chevron-up" : "mdi:chevron-down"}></ha-icon>
            ${this._showPayRecords ? "收起缴费" : "最近缴费"}
          </div>
          ` : ""}
        </div>
        ` : ""}

        <!-- 账单表格 -->
        ${this._showBills && billlist.length > 0 ? html`
        <div class="bill-section">
          <table class="bill-table">
            <thead>
              <tr>
                <th>账单期</th>
                <th>用水量(m³)</th>
                <th>表读数(m³)</th>
                <th>水费(元)</th>
                <th>污水处理费(元)</th>
                <th>总金额(元)</th>
              </tr>
            </thead>
            <tbody>
              ${billlist.map((bill) => html`
                <tr>
                  <td class="bill-period">${bill.period || "-"}</td>
                  <td class="bill-usage">${this._fmt(bill.water_usage, 1)}</td>
                  <td>${this._fmt(bill.meter_reading, 1)}</td>
                  <td>${this._fmt(bill.water_fee)}</td>
                  <td>${this._fmt(bill.service_fee)}</td>
                  <td class="bill-fee">${this._fmt(bill.total_fee)}</td>
                </tr>
              `)}
            </tbody>
          </table>
        </div>
        ` : ""}

        <!-- 缴费记录表格 -->
        ${this._showPayRecords && payRecords.length > 0 ? html`
        <div class="bill-section">
          <table class="bill-table">
            <thead>
              <tr>
                <th>缴费金额(元)</th>
                <th>账期</th>
                <th>缴费时间</th>
              </tr>
            </thead>
            <tbody>
              ${payRecords.map((record) => html`
                <tr>
                  <td class="bill-fee">${this._fmt(record.amount)}</td>
                  <td>${record.order_date || "-"}</td>
                  <td>${record.create_time || "-"}</td>
                </tr>
              `)}
            </tbody>
          </table>
        </div>
        ` : ""}
      </ha-card>
    `;
  }
}
customElements.define("hfwater-card", HfWaterCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "hfwater-card",
  name: "合肥水务卡片",
  description: "显示用水账单和账户信息的卡片",
  documentationURL: "https://github.com/Cyborg2017/ha_hfwater",
});

// 通知 HA 前端重新渲染
if (window.customCards && window.customCards.length > 0) {
  window.dispatchEvent(new CustomEvent("custom-cards-updated", { bubbles: true }));
  setTimeout(() => {
    window.dispatchEvent(new CustomEvent("custom-cards-updated", { bubbles: true }));
  }, 1000);
}
