import { useEffect, useState } from 'react'

/**
 * Lightweight weather lookup using Open-Meteo (free, no API key).
 * Returns the current condition + temperature for given coords, plus a
 * 7-day forecast used by the weekly outfit planner.
 */

export interface CurrentWeather {
  temperature: number       // °C
  condition: string         // 'Sunny', 'Cloudy', etc.
  is_day: boolean
}

export interface DailyForecast {
  date: string              // YYYY-MM-DD
  temp_max: number
  temp_min: number
  condition: string
  precipitation_mm: number
}

export interface WeatherData {
  current: CurrentWeather
  daily: DailyForecast[]
}

const _CONDITION_BY_CODE: Record<number, string> = {
  0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
  45: 'Foggy', 48: 'Foggy',
  51: 'Drizzle', 53: 'Drizzle', 55: 'Drizzle',
  61: 'Rainy', 63: 'Rainy', 65: 'Heavy rain',
  71: 'Snowy', 73: 'Snowy', 75: 'Heavy snow',
  80: 'Showers', 81: 'Showers', 82: 'Showers',
  95: 'Thunderstorm', 96: 'Thunderstorm', 99: 'Thunderstorm',
}

function describeCode(code: number): string {
  return _CONDITION_BY_CODE[code] ?? 'Mild'
}

export async function fetchWeather(lat: number, lon: number): Promise<WeatherData> {
  const url = new URL('https://api.open-meteo.com/v1/forecast')
  url.searchParams.set('latitude', String(lat))
  url.searchParams.set('longitude', String(lon))
  url.searchParams.set('current', 'temperature_2m,weather_code,is_day')
  url.searchParams.set('daily', 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum')
  url.searchParams.set('timezone', 'auto')
  url.searchParams.set('forecast_days', '7')

  const resp = await fetch(url.toString())
  if (!resp.ok) throw new Error(`Weather request failed: ${resp.status}`)
  const data = await resp.json()

  const cur = data.current ?? {}
  const d = data.daily ?? {}
  const daily: DailyForecast[] = (d.time ?? []).map((date: string, i: number) => ({
    date,
    temp_max: d.temperature_2m_max?.[i] ?? 0,
    temp_min: d.temperature_2m_min?.[i] ?? 0,
    condition: describeCode(d.weather_code?.[i] ?? 0),
    precipitation_mm: d.precipitation_sum?.[i] ?? 0,
  }))

  return {
    current: {
      temperature: cur.temperature_2m ?? 20,
      condition:   describeCode(cur.weather_code ?? 0),
      is_day:      Boolean(cur.is_day ?? 1),
    },
    daily,
  }
}

export function useWeather(coords: { lat: number; lon: number } | null) {
  const [data, setData] = useState<WeatherData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!coords) { setData(null); return }
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchWeather(coords.lat, coords.lon)
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Weather unavailable') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [coords?.lat, coords?.lon])

  return { data, loading, error }
}

/**
 * Ask the browser for geolocation. Returns null if denied or unavailable.
 * Resolves with `{lat, lon}` plus an attempt at a human label via reverse geocoding.
 */
export async function requestGeolocation(): Promise<{ lat: number; lon: number; label?: string } | null> {
  if (!('geolocation' in navigator)) return null
  return new Promise(resolve => {
    navigator.geolocation.getCurrentPosition(
      async pos => {
        const lat = pos.coords.latitude
        const lon = pos.coords.longitude
        let label: string | undefined
        try {
          const r = await fetch(`https://geocoding-api.open-meteo.com/v1/reverse?latitude=${lat}&longitude=${lon}&count=1`)
          const j = await r.json()
          const hit = j?.results?.[0]
          if (hit) label = [hit.name, hit.admin1, hit.country_code].filter(Boolean).join(', ')
        } catch { /* label is best-effort */ }
        resolve({ lat, lon, label })
      },
      () => resolve(null),
      { timeout: 8000, maximumAge: 60_000 },
    )
  })
}
