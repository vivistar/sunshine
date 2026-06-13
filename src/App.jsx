import { useEffect, useState } from 'react';
import { getDailyAffirmation } from './affirmations';
import { useWeather } from './useWeather';

function formatDate(date) {
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

function WeatherCard({ weather, loading, error }) {
  if (loading) {
    return (
      <div className="flex items-center gap-3 text-white/60 animate-pulse">
        <div className="w-8 h-8 rounded-full bg-white/20" />
        <div className="space-y-1">
          <div className="h-4 w-24 rounded bg-white/20" />
          <div className="h-3 w-32 rounded bg-white/20" />
        </div>
      </div>
    );
  }

  if (error || !weather) {
    return (
      <p className="text-white/50 text-sm">Unable to load weather.</p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="flex items-center gap-3">
        <span className="text-5xl leading-none" role="img" aria-label={weather.condition}>
          {weather.icon}
        </span>
        <div>
          <p className="text-white text-4xl font-light leading-none">
            {weather.tempF}°<span className="text-2xl">F</span>
          </p>
          <p className="text-white/70 text-sm mt-0.5">{weather.condition}</p>
        </div>
      </div>
      <div className="flex gap-6 text-white/70 text-sm">
        <div>
          <p className="text-white/40 text-xs uppercase tracking-widest">Feels Like</p>
          <p className="text-white font-medium">{weather.feelsLikeF}°F</p>
        </div>
        <div>
          <p className="text-white/40 text-xs uppercase tracking-widest">Humidity</p>
          <p className="text-white font-medium">{weather.humidity}%</p>
        </div>
        <div>
          <p className="text-white/40 text-xs uppercase tracking-widest">Wind</p>
          <p className="text-white font-medium">{weather.windMph} mph</p>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const today = new Date();
  const affirmation = getDailyAffirmation();
  const { weather, loading, error } = useWeather();

  // Gradient shifts slowly through the day based on hour
  const hour = today.getHours();
  let gradient = 'from-indigo-900 via-purple-900 to-slate-900';
  if (hour >= 5 && hour < 9) gradient = 'from-orange-800 via-rose-900 to-purple-900';
  else if (hour >= 9 && hour < 12) gradient = 'from-sky-700 via-blue-800 to-indigo-900';
  else if (hour >= 12 && hour < 17) gradient = 'from-blue-600 via-sky-700 to-blue-900';
  else if (hour >= 17 && hour < 20) gradient = 'from-orange-700 via-red-800 to-purple-900';
  else if (hour >= 20 && hour < 22) gradient = 'from-purple-900 via-indigo-900 to-slate-900';

  // Orb colors keyed to the time-of-day palette
  const orbs = hour >= 5 && hour < 9
    ? ['#f97316', '#e11d48', '#7c3aed']
    : hour >= 9 && hour < 12
    ? ['#0ea5e9', '#6366f1', '#0284c7']
    : hour >= 12 && hour < 17
    ? ['#38bdf8', '#3b82f6', '#1d4ed8']
    : hour >= 17 && hour < 20
    ? ['#f97316', '#dc2626', '#7c3aed']
    : ['#7c3aed', '#4f46e5', '#1e1b4b'];

  return (
    <div className={`min-h-screen bg-gradient-to-br ${gradient} gradient-animated flex flex-col`}>
      {/* Floating colour orbs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        {orbs.map((color, i) => (
          <div
            key={i}
            className="orb absolute"
            style={{
              background: color,
              width: `${380 + i * 120}px`,
              height: `${380 + i * 120}px`,
              top: `${[10, 50, 30][i]}%`,
              left: `${[60, 10, 75][i]}%`,
              '--dur': `${12 + i * 5}s`,
              '--tx': `${[-60, 80, -40][i]}px`,
              '--ty': `${[40, -60, 70][i]}px`,
              '--tx2': `${[30, -30, 60][i]}px`,
              '--ty2': `${[-30, 50, -50][i]}px`,
            }}
          />
        ))}
      </div>

      {/* Subtle star-like dots overlay */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden opacity-30">
        {[...Array(40)].map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full bg-white"
            style={{
              width: Math.random() * 2 + 1 + 'px',
              height: Math.random() * 2 + 1 + 'px',
              top: Math.random() * 100 + '%',
              left: Math.random() * 100 + '%',
              opacity: Math.random() * 0.6 + 0.2,
            }}
          />
        ))}
      </div>

      <div className="relative z-10 flex flex-col min-h-screen max-w-3xl mx-auto w-full px-6 py-12">

        {/* Header */}
        <header className="mb-auto">
          <p className="text-white/50 text-sm font-light tracking-widest uppercase">
            {formatDate(today)}
          </p>
          <h1 className="font-display text-white text-2xl mt-1 font-normal tracking-wide">
            Sunshine ✦
          </h1>
        </header>

        {/* Main affirmation */}
        <main className="py-16 flex flex-col gap-4">
          <p className="text-white/40 text-xs uppercase tracking-widest font-medium">
            Today's Affirmation
          </p>
          <blockquote className="font-display text-white text-3xl sm:text-4xl leading-snug font-normal italic">
            "{affirmation}"
          </blockquote>
          <div className="h-px w-16 bg-white/30 mt-2" />
        </main>

        {/* Weather section */}
        <footer className="mt-auto">
          <p className="text-white/40 text-xs uppercase tracking-widest font-medium mb-4">
            Brownsburg, Indiana
          </p>
          <WeatherCard weather={weather} loading={loading} error={error} />
          <p className="text-white/25 text-xs mt-6">
            Weather via Open-Meteo · Affirmation changes daily
          </p>
        </footer>
      </div>
    </div>
  );
}
