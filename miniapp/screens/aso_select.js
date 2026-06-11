// screens/aso_select.js — انتخاب سختی آسو

function renderAsoSelect(state) {
  const modes = [
    {
      key: "easy",
      name: "آسو رحیم",
      subtitle: "سطح آسان",
      rarityLabel: "کارت‌های معمولی",
      rewards: "+3 امتیاز / +5 XP / +10 TP",
      color: "rarity-normal",
      border: "border-rarity-normal/30",
      glow: "shadow-[0_0_15px_rgba(76,175,80,0.2)]",
      icon: "sentiment_satisfied",
    },
    {
      key: "medium",
      name: "آسو خشمگین",
      subtitle: "سطح متوسط",
      rarityLabel: "کارت‌های حماسی",
      rewards: "+5 امتیاز / +8 XP / +15 TP",
      color: "rarity-epic",
      border: "border-rarity-epic/40",
      glow: "shadow-[0_0_15px_rgba(156,39,176,0.25)]",
      icon: "sentiment_dissatisfied",
    },
    {
      key: "hard",
      name: "آسو نابودگر",
      subtitle: "سطح سخت",
      rarityLabel: "کارت‌های افسانه‌ای",
      rewards: "+8 امتیاز / +10 XP / +20 TP",
      color: "rarity-legend",
      border: "border-rarity-legend/50",
      glow: "shadow-[0_0_20px_rgba(255,152,0,0.3)]",
      icon: "whatshot",
    },
  ];

  return `
<div class="min-h-screen flex flex-col pb-8">
  <!-- Header -->
  <header class="fixed top-0 w-full z-50 bg-surface/80 backdrop-blur-xl border-b border-white/10 flex justify-between items-center px-[16px] py-4">
    <div class="flex items-center gap-3">
      <button data-action="go_home" class="text-on-surface-variant hover:text-primary transition-colors active:scale-95">
        <span class="material-symbols-outlined">arrow_back</span>
      </button>
      <div class="font-headline-lg text-headline-lg font-bold text-primary italic">TelBattle</div>
    </div>
  </header>

  <main class="pt-[80px] px-[16px] flex flex-col gap-6">
    <!-- Aso Banner -->
    <section class="mt-4 bg-surface-card border border-rarity-epic/30 rounded-xl p-4 flex items-center gap-4 relative overflow-hidden shadow-[0_0_25px_rgba(156,39,176,0.2)]">
      <div class="absolute inset-0 bg-gradient-to-r from-rarity-epic/15 to-transparent pointer-events-none"></div>
      <div class="w-16 h-16 rounded-full overflow-hidden border-2 border-rarity-epic shadow-[0_0_15px_rgba(156,39,176,0.5)] shrink-0 z-10">
        <div class="w-full h-full bg-gradient-to-br from-rarity-epic to-background-deep flex items-center justify-center">
          <span class="material-symbols-outlined text-[36px] text-white fill-icon">person</span>
        </div>
      </div>
      <div class="z-10">
        <h2 class="font-headline-md text-headline-md text-text-primary mb-1">Aso</h2>
        <p class="font-body-md text-body-md text-on-surface-variant">خدای TelBattle — سختی را انتخاب کن</p>
      </div>
    </section>

    <!-- Difficulty Cards -->
    ${modes.map(m => `
    <button data-action="select_difficulty" data-value="${m.key}"
      class="w-full bg-surface-card ${m.border} border rounded-xl p-4 ${m.glow} active:scale-95 transition-all text-right">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl bg-surface-container border border-white/10 flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-${m.color} fill-icon text-[28px]">${m.icon}</span>
        </div>
        <div class="flex-1">
          <div class="flex items-center justify-between mb-1">
            <h3 class="font-headline-sm text-headline-sm text-text-primary">${m.name}</h3>
            <span class="font-label-caps text-label-caps text-${m.color} bg-${m.color}/10 px-2 py-1 rounded">${m.subtitle}</span>
          </div>
          <p class="font-body-md text-body-md text-on-surface-variant text-sm mb-2">${m.rarityLabel}</p>
          <p class="font-label-caps text-label-caps text-outline text-xs">${m.rewards}</p>
        </div>
        <span class="material-symbols-outlined text-outline">chevron_left</span>
      </div>
    </button>`).join('')}

    <p class="text-center font-body-md text-body-md text-outline text-sm mt-2">
      در صورت باخت، ۱ قلب کم می‌شود
    </p>
  </main>
</div>`;
}
