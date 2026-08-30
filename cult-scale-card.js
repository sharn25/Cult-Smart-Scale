/**
 * Cult Smart Scale Lovelace Card for Home Assistant
 * Features:
 *  - Arc gauge matching the modern health app UI with authentic curved textPath labels
 *  - 3 segmented zones (Underweight, Normal, Overweight)
 *  - Seamless integrated round marker bead on the bar track (No needle)
 *  - Refined compact BMI display matching the reference scale proportions
 *  - Profile pill bar with auto-detected Gender, Age, Weight, and Height
 *  - Colored-dot metric cards matching modern fitness dashboard layouts
 *  - Full light & dark mode native Home Assistant support
 */

class CultScaleCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  static getStubConfig() {
    return {
      type: "custom:cult-scale-card",
      name: "Cult Smart Scale",
      person_prefix: "sensor.cult_scale_sharanjit",
    };
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Invalid configuration");
    }
    this._config = Object.assign(
      {
        name: "Cult Smart Scale",
        title: "",
        person_prefix: "",
        entity: "",
        show_metrics_grid: true,
        show_profile_footer: true,
        unit_system: "metric", // "metric" or "imperial"
      },
      config
    );
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateCard();
  }

  /**
   * Search for an entity state and its attributes using fuzzy key matching
   */
  _findEntity(metricKey) {
    if (!this._hass) return null;

    // 1. Direct YAML config override
    if (this._config[metricKey]) {
      const stateObj = this._hass.states[this._config[metricKey]];
      if (stateObj) return stateObj;
    }

    // Possible slug suffixes for each metric key
    const keyPatterns = {
      weight: ["_weight", "_last_weight", "_weight_kg"],
      bmi: ["_bmi"],
      body_fat: ["_body_fat", "_body_fat_percentage", "_fat_percentage"],
      body_fat_mass: ["_body_fat_mass", "_body_fat_kg"],
      fat_free_mass: ["_fat_free_mass", "_fat_free_mass_kg"],
      muscle_mass: ["_muscle_mass", "_muscle_mass_kg"],
      muscle_percentage: ["_muscle_rate", "_muscle_percentage"],
      skeletal_muscle: ["_skeletal_muscle", "_skeletal_muscle_kg"],
      water: ["_total_body_water", "_body_water", "_water", "_water_percentage"],
      water_mass: ["_water_mass", "_water_kg"],
      bone_mass: ["_bone_mass", "_bone_mass_kg"],
      protein: ["_protein", "_protein_percentage"],
      subcutaneous_fat: ["_subcutaneous_fat", "_subcutaneous_fat_percentage"],
      visceral_fat: ["_visceral_fat_level", "_visceral_fat"],
      bmr: ["_basal_metabolic_rate", "_bmr", "_basal_metabolism", "_bmr_kcal"],
      body_age: ["_metabolic_body_age", "_metabolic_age", "_body_age"],
      ideal_weight: ["_ideal_weight", "_ideal_weight_kg"],
      body_type: ["_body_classification", "_body_type"],
      heart_rate: ["_heart_rate", "_last_heart_rate"],
    };

    const patterns = keyPatterns[metricKey] || [`_${metricKey}`];

    // 2. Search under person_prefix (e.g. sensor.cult_scale_sharanjit)
    const basePrefix = (
      this._config.person_prefix ||
      (this._config.entity ? this._config.entity.replace(/_[a-z0-9_]+$/, "") : "")
    ).toLowerCase();

    if (basePrefix) {
      for (const pat of patterns) {
        const candidateId = `${basePrefix}${pat}`;
        if (this._hass.states[candidateId]) {
          return this._hass.states[candidateId];
        }
      }
    }

    // 3. Global search in hass.states for matching entity_ids
    for (const entityId of Object.keys(this._hass.states)) {
      if (basePrefix && !entityId.toLowerCase().startsWith(basePrefix)) {
        continue;
      }
      for (const pat of patterns) {
        if (entityId.toLowerCase().endsWith(pat)) {
          return this._hass.states[entityId];
        }
      }
    }

    return null;
  }

  _getEntityState(metricKey, fallback = null) {
    const entity = this._findEntity(metricKey);
    if (entity && entity.state !== "unavailable" && entity.state !== "unknown") {
      return entity.state;
    }
    return fallback;
  }

  _getBMIRanges() {
    return {
      min: 13.0,
      max: 37.0,
      label: "BMI",
      zones: [
        { name: "Underweight", minVal: 13.0, maxVal: 18.5, color: "rgba(56, 189, 248, 0.22)", activeColor: "#38BDF8" },
        { name: "Normal", minVal: 18.5, maxVal: 25.0, color: "rgba(34, 197, 94, 0.22)", activeColor: "#22C55E" },
        { name: "Overweight", minVal: 25.0, maxVal: 37.0, color: "rgba(255, 91, 85, 0.22)", activeColor: "#FF5B55" },
      ],
    };
  }

  _calculateAngle(value) {
    const min = 13.0;
    const max = 37.0;
    const clamped = Math.max(min, Math.min(max, value));

    // Continuous smooth mapping:
    // Zone 1: Underweight (13.0 to 18.5) -> Angle: -180 deg to -125 deg (span 55 deg)
    // Zone 2: Normal (18.5 to 25.0)      -> Angle: -125 deg to -55 deg (span 70 deg)
    // Zone 3: Overweight (25.0 to 37.0)  -> Angle: -55 deg to 0 deg (span 55 deg)
    if (clamped <= 18.5) {
      const ratio = (clamped - 13.0) / (18.5 - 13.0);
      return -180 + ratio * 55;
    } else if (clamped <= 25.0) {
      const ratio = (clamped - 18.5) / (25.0 - 18.5);
      return -125 + ratio * 70;
    } else {
      const ratio = (clamped - 25.0) / (37.0 - 25.0);
      return -55 + ratio * 55;
    }
  }

  _formatHeight(cm) {
    if (!cm || isNaN(cm)) return "--";
    if (this._config.unit_system === "imperial") {
      const totalInches = cm / 2.54;
      const feet = Math.floor(totalInches / 12);
      const inches = Math.round(totalInches % 12);
      return `${feet} ft ${inches} in`;
    }
    return `${Math.round(cm)} cm`;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          contain: content;
        }
        ha-card {
          background: var(--ha-card-background, var(--card-background-color, var(--ha-card-background, #ffffff)));
          border-radius: var(--ha-card-border-radius, 12px);
          border-width: var(--ha-card-border-width, 1px);
          border-style: solid;
          border-color: var(--ha-card-border-color, var(--divider-color, rgba(127, 127, 127, 0.2)));
          box-shadow: var(--ha-card-box-shadow, none);
          box-sizing: border-box;
          padding: 16px 20px 20px 20px;
          color: var(--primary-text-color, #212121);
          font-family: var(--ha-card-font-family, -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif);
          position: relative;
          overflow: hidden;
          cursor: pointer;
        }

        /* Top Header */
        .header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 6px;
        }
        .header-left {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .header-subtitle {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 1.2px;
          text-transform: uppercase;
          color: var(--secondary-text-color, #727272);
          opacity: 0.85;
        }
        .header-title {
          font-size: 18px;
          font-weight: 700;
          color: var(--primary-text-color, #212121);
          letter-spacing: -0.3px;
        }
        .header-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 38px;
          height: 38px;
          border-radius: var(--ha-card-border-radius, 12px);
          background: rgba(127, 127, 127, 0.06);
          border: 1px solid var(--ha-card-border-color, var(--divider-color, rgba(127, 127, 127, 0.12)));
          color: var(--primary-text-color, #212121);
          opacity: 0.85;
          flex-shrink: 0;
        }
        .header-icon ha-icon {
          --mdc-icon-size: 20px;
        }

        /* Gauge Area */
        .gauge-container {
          position: relative;
          width: 100%;
          max-width: 320px;
          margin: 10px auto 4px auto;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .gauge-svg {
          width: 100%;
          height: auto;
          overflow: visible;
        }
        .gauge-marker-group {
          transition: transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        /* Centered BMI Display (Bottom Center of Arc) */
        .gauge-center-content {
          position: absolute;
          bottom: 4px;
          left: 0;
          right: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          pointer-events: none;
          text-align: center;
        }
        .center-bmi-label {
          font-size: 11.5px;
          font-weight: 400;
          color: var(--primary-text-color, #212121);
          letter-spacing: 1px;
          text-transform: uppercase;
          opacity: 0.85;
          margin-bottom: 2px;
        }
        .center-bmi-val {
          font-size: 24px;
          font-weight: 600;
          line-height: 1.05;
          letter-spacing: -0.5px;
          margin-top: 1px;
          color: #22C55E;
          transition: color 0.4s ease;
        }

        /* Profile Summary Pill Bar */
        .profile-footer {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 8px;
          margin-top: 16px;
          padding: 12px 10px;
          border-radius: var(--ha-card-border-radius, 12px);
          background: rgba(127, 127, 127, 0.04);
          border: 1px solid var(--ha-card-border-color, var(--divider-color, rgba(127, 127, 127, 0.12)));
          text-align: center;
        }
        .profile-item {
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .profile-label {
          font-size: 10.5px;
          color: var(--secondary-text-color, #727272);
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.6px;
          margin-bottom: 3px;
          opacity: 0.85;
        }
        .profile-val {
          font-size: 14px;
          font-weight: 700;
          color: var(--primary-text-color, #212121);
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .profile-val ha-icon {
          --mdc-icon-size: 16px;
          color: var(--state-active-color, #10B981);
        }

        /* Secondary Metrics Breakdown Grid - 3-Column Compact & Minimalist */
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-top: 14px;
        }
        .metric-card {
          background: rgba(127, 127, 127, 0.035);
          padding: 10px 10px 9px 10px;
          border-radius: var(--ha-card-border-radius, 12px);
          border: 1px solid var(--ha-card-border-color, var(--divider-color, rgba(127, 127, 127, 0.1)));
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-height: 60px;
          cursor: pointer;
          user-select: none;
          transition: transform 0.2s ease, background 0.2s ease, border-color 0.2s ease;
        }
        .metric-card:hover {
          background: rgba(127, 127, 127, 0.08);
          border-color: var(--ha-card-border-color, var(--divider-color, rgba(127, 127, 127, 0.2)));
          transform: translateY(-1.5px);
        }
        .metric-card:active {
          transform: translateY(0.5px);
          opacity: 0.85;
        }
        .metric-card-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 3px;
        }
        .metric-card-label {
          font-size: 11px;
          font-weight: 500;
          color: var(--secondary-text-color, #727272);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .metric-card-unit {
          font-size: 10.5px;
          font-weight: 500;
          color: var(--secondary-text-color, #727272);
          opacity: 0.8;
          margin-left: 2px;
        }
        .metric-card-bottom {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
        }
        .metric-card-val {
          font-size: 16px;
          font-weight: 700;
          color: var(--primary-text-color, #212121);
          line-height: 1.1;
          letter-spacing: -0.3px;
        }
        .metric-arrow-btn {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          border: 1px solid var(--ha-card-border-color, var(--divider-color, rgba(127, 127, 127, 0.25)));
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--secondary-text-color, #727272);
          opacity: 0.65;
          transition: transform 0.2s ease, opacity 0.2s ease;
        }
        .metric-card:hover .metric-arrow-btn {
          opacity: 1;
          transform: translateX(1px);
        }
        .metric-arrow-btn svg {
          width: 8px;
          height: 8px;
        }
      </style>

      <ha-card>
        <!-- Header Section -->
        <div class="header">
          <div class="header-left">
            <span class="header-subtitle">BODY COMPOSITION</span>
            <span class="header-title" id="card-title">${this._config.title || this._config.name || "Cult Smart Scale"}</span>
          </div>
          <div class="header-icon">
            <ha-icon icon="mdi:scale-bathroom"></ha-icon>
          </div>
        </div>

        <!-- Main Gauge Visualization (Matching Image with Curved Text & Integrated Bead) -->
        <div class="gauge-container" data-metric="bmi" style="cursor: pointer;" title="View BMI History">
          <svg class="gauge-svg" viewBox="0 0 280 155">
            <defs>
              <!-- Outer Path Guide for Curved Category Labels (Radius 116) -->
              <path id="guide-outer-labels" d="M 28 146 A 112 112 0 0 1 252 146" fill="none" />
              <!-- Inner Path Guide for Curved Boundary Scale Numbers (Radius 82) -->
              <path id="guide-inner-ticks" d="M 58 146 A 82 82 0 0 1 222 146" fill="none" />
            </defs>

            <!-- Segmented Arc Paths (Underweight, Normal, Overweight) -->
            <g id="gauge-segments"></g>

            <!-- Outer Category Labels Curved along the Arc -->
            <text font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif" font-weight="300" font-size="12.5" fill="var(--secondary-text-color, #727272)">
              <textPath href="#guide-outer-labels" startOffset="14%" text-anchor="middle" id="lbl-underweight">Underweight</textPath>
              <textPath href="#guide-outer-labels" startOffset="50%" text-anchor="middle" id="lbl-normal">Normal</textPath>
              <textPath href="#guide-outer-labels" startOffset="86%" text-anchor="middle" id="lbl-overweight">Overweight</textPath>
            </text>

            <!-- Inner Boundary Ticks Curved along the Arc -->
            <text font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif" font-weight="500" font-size="10" fill="var(--secondary-text-color, #727272)" opacity="0.85">
              <textPath href="#guide-inner-ticks" startOffset="4%" text-anchor="middle">13.0</textPath>
              <textPath href="#guide-inner-ticks" startOffset="28%" text-anchor="middle">18.5</textPath>
              <textPath href="#guide-inner-ticks" startOffset="72%" text-anchor="middle">25.0</textPath>
              <textPath href="#guide-inner-ticks" startOffset="96%" text-anchor="middle">37.0</textPath>
            </text>

            <!-- Seamless Integrated Round Marker Bead on Arc Centerline (R=98) -->
            <g id="marker-group" class="gauge-marker-group" transform="rotate(-180 140 146)">
              <circle cx="238" cy="146" r="8.5" id="marker-bead" fill="#22C55E" />
            </g>
          </svg>

          <!-- Centered Refined BMI Display -->
          <div class="gauge-center-content">
            <div class="center-bmi-label">BMI</div>
            <div class="center-bmi-val" id="center-val">--</div>
          </div>
        </div>

        <!-- User Stats / Profile Footer (Auto-discovered) -->
        ${this._config.show_profile_footer
        ? `
          <div class="profile-footer">
            <div class="profile-item">
              <span class="profile-label">Gender</span>
              <span class="profile-val" id="profile-gender">
                <ha-icon icon="mdi:gender-male"></ha-icon>
                <span>Male</span>
              </span>
            </div>
            <div class="profile-item">
              <span class="profile-label">Age</span>
              <span class="profile-val" id="profile-age">-- Yrs</span>
            </div>
            <div class="profile-item" data-metric="weight" style="cursor: pointer;" title="View Weight History">
              <span class="profile-label">Weight</span>
              <span class="profile-val" id="profile-weight">-- kg</span>
            </div>
            <div class="profile-item">
              <span class="profile-label">Height</span>
              <span class="profile-val" id="profile-height">-- cm</span>
            </div>
          </div>
        `
        : ""
      }

        <!-- Secondary Metrics Breakdown Grid - 3-Column Compact & Minimalist -->
        ${this._config.show_metrics_grid
        ? `
          <div class="metrics-grid" id="metrics-grid">
            <!-- Heart Rate -->
            <div class="metric-card" data-metric="heart_rate" title="View Heart Rate History">
              <div class="metric-card-top">
                <span class="metric-card-label">Heart rate</span>
                <span class="metric-card-unit">bpm</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-hr">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- Body Fat -->
            <div class="metric-card" data-metric="body_fat" title="View Body Fat History">
              <div class="metric-card-top">
                <span class="metric-card-label">Body fat</span>
                <span class="metric-card-unit">%</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-fat">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- Muscle Mass -->
            <div class="metric-card" data-metric="muscle_mass" title="View Muscle Mass History">
              <div class="metric-card-top">
                <span class="metric-card-label">Muscle mass</span>
                <span class="metric-card-unit">kg</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-muscle">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- Skeletal Muscle -->
            <div class="metric-card" data-metric="skeletal_muscle" title="View Skeletal Muscle History">
              <div class="metric-card-top">
                <span class="metric-card-label">Skeletal mus.</span>
                <span class="metric-card-unit">kg</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-skeletal">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- Water -->
            <div class="metric-card" data-metric="water" title="View Body Water History">
              <div class="metric-card-top">
                <span class="metric-card-label">Water</span>
                <span class="metric-card-unit">%</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-water">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- Bone Mass -->
            <div class="metric-card" data-metric="bone_mass" title="View Bone Mass History">
              <div class="metric-card-top">
                <span class="metric-card-label">Bone mass</span>
                <span class="metric-card-unit">kg</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-bone">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- BMR -->
            <div class="metric-card" data-metric="bmr" title="View Basal Metabolic Rate History">
              <div class="metric-card-top">
                <span class="metric-card-label">BMR</span>
                <span class="metric-card-unit">kcal</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-bmr">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- Visceral Fat -->
            <div class="metric-card" data-metric="visceral_fat" title="View Visceral Fat History">
              <div class="metric-card-top">
                <span class="metric-card-label">Visceral fat</span>
                <span class="metric-card-unit">lvl</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-visceral">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>

            <!-- Body Age -->
            <div class="metric-card" data-metric="body_age" title="View Metabolic Body Age History">
              <div class="metric-card-top">
                <span class="metric-card-label">Body age</span>
                <span class="metric-card-unit">yrs</span>
              </div>
              <div class="metric-card-bottom">
                <span class="metric-card-val" id="grid-age">--</span>
                <div class="metric-arrow-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
              </div>
            </div>
          </div>
        `
        : ""
      }
      </ha-card>
    `;

    // Attach click events for hass-more-info popup dialog
    this.shadowRoot.querySelectorAll("[data-metric]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const metricKey = el.getAttribute("data-metric");
        this._openMoreInfo(metricKey);
      });
    });
  }

  _openMoreInfo(metricKey) {
    const entity = this._findEntity(metricKey);
    if (!entity) return;
    const event = new CustomEvent("hass-more-info", {
      detail: { entityId: entity.entity_id },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  _generateSegmentedArc(activeZoneIndex) {
    const cx = 140;
    const cy = 146;
    const r = 98;
    const strokeWidth = 8;
    const gapDeg = 6.0;

    const zones = [
      { name: "underweight", startDeg: -180, endDeg: -125, color: "rgba(56, 189, 248, 0.22)", activeColor: "#38BDF8" },
      { name: "normal", startDeg: -125, endDeg: -55, color: "rgba(34, 197, 94, 0.22)", activeColor: "#22C55E" },
      { name: "overweight", startDeg: -55, endDeg: 0, color: "rgba(255, 91, 85, 0.22)", activeColor: "#FF5B55" },
    ];

    let paths = "";
    zones.forEach((z, i) => {
      const sDeg = z.startDeg + gapDeg / 2;
      const eDeg = z.endDeg - gapDeg / 2;

      const sRad = (sDeg * Math.PI) / 180;
      const eRad = (eDeg * Math.PI) / 180;

      const x1 = cx + r * Math.cos(sRad);
      const y1 = cy + r * Math.sin(sRad);
      const x2 = cx + r * Math.cos(eRad);
      const y2 = cy + r * Math.sin(eRad);

      const isActive = i === activeZoneIndex;
      const strokeColor = isActive ? z.activeColor : z.color;
      const currentWidth = isActive ? strokeWidth + 1 : strokeWidth;
      const opacity = isActive ? 1.0 : 0.85;

      const pathData = `M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${r} ${r} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
      paths += `<path d="${pathData}" fill="none" stroke="${strokeColor}" stroke-width="${currentWidth}" stroke-linecap="round" opacity="${opacity}" />`;
    });

    return paths;
  }

  _updateCard() {
    if (!this._hass || !this.shadowRoot) return;

    // Retrieve all entity values
    const weightObj = this._findEntity("weight");
    const weight = weightObj ? parseFloat(weightObj.state) : 0;

    const bmi = parseFloat(this._getEntityState("bmi", 0));
    const bodyFat = parseFloat(this._getEntityState("body_fat", 0));
    const muscle = parseFloat(this._getEntityState("muscle_mass", 0));
    const skeletal = parseFloat(this._getEntityState("skeletal_muscle", 0));
    const water = parseFloat(this._getEntityState("water", 0));
    const bone = parseFloat(this._getEntityState("bone_mass", 0));
    const bmr = this._getEntityState("bmr", "--");
    const visceral = this._getEntityState("visceral_fat", "--");
    const bodyAge = this._getEntityState("body_age", "--");
    const heartRate = this._getEntityState("heart_rate", "--");

    // 1. Auto-discover Profile attributes from entity extra_state_attributes
    const attrs = weightObj ? weightObj.attributes || {} : {};
    const autoGender = attrs.gender || this._config.gender || "male";
    const autoAge = attrs.age || this._config.age || (bodyAge !== "--" ? bodyAge : null);
    const autoHeightCm = attrs.height_cm || this._config.height_cm || (this._config.height ? parseFloat(this._config.height) : null);

    // Update Profile Footer
    const isMale = String(autoGender).toLowerCase() === "male";
    const genderEl = this.shadowRoot.getElementById("profile-gender");
    if (genderEl) {
      genderEl.innerHTML = `<ha-icon icon="${isMale ? "mdi:gender-male" : "mdi:gender-female"}"></ha-icon> <span>${isMale ? "Male" : "Female"}</span>`;
    }

    const ageEl = this.shadowRoot.getElementById("profile-age");
    if (ageEl) {
      ageEl.textContent = autoAge ? `${autoAge} Yrs` : "-- Yrs";
    }

    const weightEl = this.shadowRoot.getElementById("profile-weight");
    if (weightEl) {
      weightEl.textContent = weight > 0 ? `${weight.toFixed(1)} kg` : "-- kg";
    }

    const heightEl = this.shadowRoot.getElementById("profile-height");
    if (heightEl) {
      heightEl.textContent = this._config.height || (autoHeightCm ? this._formatHeight(autoHeightCm) : "-- cm");
    }

    // 2. Update Secondary Grid
    const fatGrid = this.shadowRoot.getElementById("grid-fat");
    if (fatGrid) fatGrid.textContent = bodyFat > 0 ? bodyFat.toFixed(1) : "--";

    const musGrid = this.shadowRoot.getElementById("grid-muscle");
    if (musGrid) musGrid.textContent = muscle > 0 ? muscle.toFixed(1) : "--";

    const skelGrid = this.shadowRoot.getElementById("grid-skeletal");
    if (skelGrid) skelGrid.textContent = skeletal > 0 ? skeletal.toFixed(1) : "--";

    const waterGrid = this.shadowRoot.getElementById("grid-water");
    if (waterGrid) waterGrid.textContent = water > 0 ? water.toFixed(1) : "--";

    const boneGrid = this.shadowRoot.getElementById("grid-bone");
    if (boneGrid) boneGrid.textContent = bone > 0 ? bone.toFixed(1) : "--";

    const bmrGrid = this.shadowRoot.getElementById("grid-bmr");
    if (bmrGrid) bmrGrid.textContent = bmr;

    const viscGrid = this.shadowRoot.getElementById("grid-visceral");
    if (viscGrid) viscGrid.textContent = visceral;

    const ageGrid = this.shadowRoot.getElementById("grid-age");
    if (ageGrid) ageGrid.textContent = bodyAge;

    const hrGrid = this.shadowRoot.getElementById("grid-hr");
    if (hrGrid) hrGrid.textContent = heartRate;

    // 3. Determine Active Zone & Colors
    let activeZoneIndex = 1;
    let activeColor = "#22C55E";

    if (bmi > 0) {
      if (bmi < 18.5) {
        activeZoneIndex = 0;
        activeColor = "#38BDF8";
      } else if (bmi <= 24.9) {
        activeZoneIndex = 1;
        activeColor = "#22C55E";
      } else {
        activeZoneIndex = 2;
        activeColor = "#FF5B55";
      }
    }

    // Center Big BMI Value
    const centerValEl = this.shadowRoot.getElementById("center-val");
    if (centerValEl) {
      centerValEl.textContent = bmi > 0 ? `${bmi.toFixed(1)}` : "--";
      centerValEl.style.color = activeColor;
    }

    // Update Arc Segments
    const segContainer = this.shadowRoot.getElementById("gauge-segments");
    if (segContainer) {
      segContainer.innerHTML = this._generateSegmentedArc(activeZoneIndex);
    }

    // Highlight Active Category Label
    const lblUnder = this.shadowRoot.getElementById("lbl-underweight");
    const lblNorm = this.shadowRoot.getElementById("lbl-normal");
    const lblOver = this.shadowRoot.getElementById("lbl-overweight");

    if (lblUnder) lblUnder.style.fill = activeZoneIndex === 0 ? "#38BDF8" : "var(--secondary-text-color, #727272)";
    if (lblNorm) lblNorm.style.fill = activeZoneIndex === 1 ? "#22C55E" : "var(--secondary-text-color, #727272)";
    if (lblOver) lblOver.style.fill = activeZoneIndex === 2 ? "#FF5B55" : "var(--secondary-text-color, #727272)";

    // Update Seamless Integrated Round Marker Bead
    const markerGroup = this.shadowRoot.getElementById("marker-group");
    const markerBead = this.shadowRoot.getElementById("marker-bead");

    if (markerGroup && markerBead) {
      const angle = bmi > 0 ? this._calculateAngle(bmi) : -180;
      markerGroup.setAttribute("transform", `rotate(${angle.toFixed(1)} 140 146)`);
      markerBead.setAttribute("fill", activeColor);
    }
  }

  getCardSize() {
    return 4;
  }
}

// Register Custom Element
if (!customElements.get("cult-scale-card")) {
  customElements.define("cult-scale-card", CultScaleCard);
}

// Register in Lovelace Card Picker window
window.customCards = window.customCards || [];
window.customCards.push({
  type: "cult-scale-card",
  name: "Cult Smart Scale Card",
  description: "A modern health app BMI gauge card with curved text and biometrics breakdown.",
  preview: true,
  documentationURL: "https://github.com/sharanjit/cult_smart_scale",
});
console.info(
  "%c CULT-SCALE-CARD %c v1.0.0 Loaded ",
  "color: white; background: #03a9f4; font-weight: bold; border-radius: 4px;",
  "color: #03a9f4; background: transparent;"
);
