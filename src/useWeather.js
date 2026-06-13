import { useState, useEffect } from 'react';

export const LOCATIONS = {
  brownsburg: { name: 'Brownsburg, Indiana', lat: 39.8442, lon: -86.3936 },
  chicago: { name: 'Chicago, Illinois', lat: 41.8781, lon: -87.6298 },
};

const WMO_CODES = {
  0: { label: 'Clear Sky', icon: '☀️' },
  1: { label: 'Mainly Clear', icon: '🌤️' },
  2: { label: 'Partly Cloudy', icon: '⛅' },
  3: { label: 'Overcast', icon: '☁️' },
  45: { label: 'Foggy', icon: '🌫️' },
  48: { label: 'Icy Fog', icon: '🌫️' },
  51: { label: 'Light Drizzle', icon: '🌦️' },
  53: { label: 'Drizzle', icon: '🌦️' },
  55: { label: 'Heavy Drizzle', icon: '🌧️' },
  61: { label: 'Light Rain', icon: '🌧️' },
  63: { label: 'Rain', icon: '🌧️' },
  65: { label: 'Heavy Rain', icon: '🌧️' },
  71: { label: 'Light Snow', icon: '🌨️' },
  73: { label: 'Snow', icon: '❄️' },
  75: { label: 'Heavy Snow', icon: '❄️' },
  77: { label: 'Snow Grains', icon: '🌨️' },
  80: { label: 'Light Showers', icon: '🌦️' },
  81: { label: 'Showers', icon: '🌧️' },
  82: { label: 'Heavy Showers', icon: '⛈️' },
  85: { label: 'Snow Showers', icon: '🌨️' },
  86: { label: 'Heavy Snow Showers', icon: '🌨️' },
  95: { label: 'Thunderstorm', icon: '⛈️' },
  96: { label: 'Thunderstorm w/ Hail', icon: '⛈️' },
  99: { label: 'Thunderstorm w/ Heavy Hail', icon: '⛈️' },
};

function cToF(c) {
  return Math.round((c * 9) / 5 + 32);
}

export function useWeather(lat, lon) {
  const [weather, setWeather] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchWeather() {
      try {
        const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weathercode&temperature_unit=celsius&wind_speed_unit=mph&timezone=America%2FChicago`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('Weather fetch failed');
        const data = await res.json();
        const c = data.current;
        const code = c.weathercode;
        const meta = WMO_CODES[code] ?? { label: 'Unknown', icon: '🌡️' };
        setWeather({
          tempF: cToF(c.temperature_2m),
          feelsLikeF: cToF(c.apparent_temperature),
          humidity: c.relative_humidity_2m,
          windMph: Math.round(c.wind_speed_10m),
          condition: meta.label,
          icon: meta.icon,
        });
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }
    fetchWeather();
  }, [lat, lon]);

  return { weather, loading, error };
}
