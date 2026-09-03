// Hand-written from docs/openapi.json (FarmShield AI backend v0.2).

export type Level = 'LOW' | 'MEDIUM' | 'HIGH'
export type HealthLabel = 'GOOD' | 'FAIR' | 'POOR'
export type Scenario = 'normal' | 'dry_spell' | 'heavy_rain'
export type Crop = 'maize' | 'beans' | 'potatoes' | 'tomatoes' | 'kale'

export interface RiskSummary {
  assessment_id: number
  farm_id: number
  assessed_at: string
  overall_score: number
  overall_level: Level
  overall_label: string
  stage: string
  insurance_triggered: boolean
  scenario: string | null
}

export interface Farm {
  id: number
  farm_name: string
  farmer_name: string
  phone: string
  language: 'en' | 'sw'
  crop: Crop
  crop_display: string
  planting_date: string
  lat: number
  lon: number
  area_ha: number | null
  county: string | null
  stage: string
  days_after_planting: number
  latest_risk: RiskSummary | null
}

export interface FarmCreate {
  farmer_name: string
  phone: string
  language: 'en' | 'sw'
  farm_name: string
  crop: Crop
  planting_date: string
  lat: number
  lon: number
  area_ha?: number | null
}

export interface StageOut {
  name: string
  day_after_planting: number
  day_in_stage: number
  stage_length_days: number
  progress: number
  water_need_mm_week: number
  sensitivity: number
  is_critical: boolean
}

export interface SubScore {
  score: number
  level: Level
  reasons: string[]
  label?: HealthLabel | null
}

export interface Overall {
  score: number
  level: Level
  label: string
  weights: Record<string, number>
}

export interface Policy {
  type: 'drought' | 'excess_rain' | 'heat'
  window_days: number
  rainfall_threshold_mm?: number | null
  temp_threshold_c?: number | null
  hot_days_threshold?: number | null
  critical_stages_only?: boolean
}

export interface InsuranceTrigger {
  triggered: boolean
  rule: string
  evidence: Record<string, unknown>
  confidence: number
  policy: Record<string, unknown>
}

export interface Advice {
  en: string
  sw: string
  source: 'gemini' | 'fallback'
  sms_en: string
  sms_sw: string
}

export interface Risk {
  assessment_id: number
  farm_id: number
  farm_name: string
  crop: Crop
  stage: StageOut
  overall: Overall
  sub_scores: {
    drought: SubScore
    flood: SubScore
    heat: SubScore
    crop_health: SubScore
  }
  insurance_trigger: InsuranceTrigger
  advice: Advice
  assessed_at: string
  scenario: string | null
  data_sources: string[]
  readings_used: number
  window_days: number
  ndvi: number | null
}

export interface RiskHistoryItem {
  assessment_id: number
  assessed_at: string
  scenario: string | null
  stage: string
  overall_score: number
  overall_level: Level
  drought: number
  flood: number
  heat: number
  crop_health: number
  insurance_triggered: boolean
}

export interface WeatherReading {
  date: string
  rainfall_mm: number
  temp_max_c: number
  temp_min_c: number
  humidity_pct: number
  soil_moisture_pct: number
  solar_radiation_wm2: number | null
  wind_speed_ms: number | null
}

export interface WeatherHistory {
  farm_id: number
  source: string
  days: number
  readings: WeatherReading[]
}

export interface ScenarioState {
  scenario: Scenario
  provider: string
  available: string[]
}

export interface ScenarioSwitch {
  scenario: Scenario
  reassessed: (RiskSummary | null)[]
}

export interface AlertRequest {
  language?: 'en' | 'sw'
  force?: boolean
  message?: string
}

export interface AlertPreview {
  farm_id: number
  assessment_id: number
  would_send: boolean
  reason: string
  recipient: string
  language: 'en' | 'sw'
  message: string
  chars: number
  level: Level
  score: number
  last_alert_id: number | null
  last_alert_at: string | null
  sender: string
}

export interface Alert {
  id: number
  farm_id: number
  assessment_id: number | null
  channel: string
  recipient: string
  language: string
  message: string
  chars: number
  status: string
  provider: string
  source: string
  trigger_reason: string | null
  provider_message_id: string | null
  error: string | null
  created_at: string
}

export interface AlertSendOut {
  farm_id: number
  sent: boolean
  reason: string
  alert: Alert | null
}

export interface PartnerInfo {
  client: string
  organisation_type: string
  request_count: number
  last_used_at: string | null
}

export interface BulkRisk {
  count: number
  summary: {
    high_risk: number
    medium_risk: number
    low_risk: number
    insurance_triggered: number
    mean_score: number | null
  }
  results: Risk[]
  errors: { farm_id: number | string; error: string }[]
}

export interface TriggerCheckIn {
  farm_id: number
  policy: Policy
  scenario?: Scenario | null
}

export interface TriggerCheckOut {
  farm_id: number
  farm_name: string
  crop: Crop
  stage: string
  triggered: boolean
  rule: string
  evidence: Record<string, unknown>
  confidence: number
  policy: Record<string, unknown>
  assessed_at: string
  scenario: string | null
  data_sources: string[]
}
