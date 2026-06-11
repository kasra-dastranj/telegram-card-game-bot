// screens/card_select.js — انتخاب کارت

const RARITY_COLORS = {
  normal: { label: "عادی", color: "rarity-normal", badge: "NORMAL" },
  epic: { label: "حماسی", color: "rarity-epic", badge: "EPIC" },
  legend: { label: "افسانه‌ای", color: "rarity-legend", badge: "LEGEND" },
  rare: { label: "نادر", color: "rarity-rare", badge: "RARE" },
};

const STAT_ICONS = {
  power: { icon: "bolt", color: "rarity-rare", label: "قدرت" },
  speed: { icon: "directions_run", color: "primary", label: "سرعت" },
  iq: { icon: "psychology", color: "secondary", label: "هوش" },
  popularity: { icon: "favorite", color: "rarity-epic", label: "شهرت" },
};

function renderCardSelect(state) {
  const cards = state.cards || [];
  const selectedId = state.selectedCardId;
  const selectedCard = state.selectedCard;
  const loading = state.loading;

  const rarityFilters = [
    { key: "all", label: "همه" },
    { key: "normal", label: "عادی" },
    { key: "epic", label: "حماسی" },
    { key: "legend", label: "افسانه‌ای" },
    { key: "rare", label: "نادر" },
  ];

  const cardGrid = loading
    ? `<div class="col-span-2 flex justify-center py-12">
        <div class="text-on-surface-variant font-body-md">در حال بارگذاری کارت‌ها...</div>
      </div>`
    : cards.length === 0
    ? `<div class="col-span-2 flex justify-center py-12">
        <div class="text-on-surface-variant font-body-md">هیچ کارتی پیدا نشد</div>
      </div>`
    : cards.map(card => {
        const rarity = RARITY_COLORS[card.rarity] || RARITY_COLORS.normal;
        const isSelected = card.card_id === selectedId;
        const isCooldown = card.is_in_cooldown;

        return `
<div data-action="${isCooldown ? '' : 'select_card'}" data-value="${card.card_id}"
  class="bg-surface-card rounded-xl border ${isSelected ? 'card-selected border-secondary' : 'border-outline-variant/30'}
         relative overflow-hidden ${isCooldown ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer active:scale-95'} transition-all">
  ${isCooldown ? `<div class="absolute inset-0 z-10 flex items-center justify-center bg-black/40 backdrop-blur-[2px]">
    <span class="material-symbols-outlined text-[48px] text-white">hourglass_empty</span>
  </div>` : ''}
  <div class="p-2 flex gap-3 items-center border-b border-white/5">
    <div class="w-16 h-16 rounded overflow-hidden relative shrink-0 bg-surface-container-high flex items-center justify-center">
      ${card.image_path
        ? `<img src="${card.image_path}" alt="${card.name}" class="w-full h-full object-cover"/>`
        : `<span class="material-symbols-outlined text-[36px] text-outline fill-icon">person</span>`}
      <div class="absolute top-0 right-0 bg-${rarity.color} text-white text-[10px] font-bold px-1.5 py-0.5 rounded-bl">
        ${rarity.badge}
      </div>
    </div>
    <div class="flex-1 min-w-0">
      <h3 class="font-headline-sm text-[16px] leading-tight text-text-primary truncate">${card.name}</h3>
    </div>
  </div>
  <div class="grid grid-cols-2 gap-1 p-2 bg-surface-container-low/50">
    ${Object.entries(STAT_ICONS).map(([key, s]) => `
    <div class="flex items-center gap-1">
      <span class="material-symbols-outlined text-[14px] text-${s.color} fill-icon">${s.icon}</span>
      <span class="font-stat-numeric text-[14px]">${card[key]}</span>
    </div>`).join('')}
  </div>
</div>`;
      }).join('');

  // Bottom sheet برای کارت انتخاب‌شده
  const bottomSheet = selectedCard ? `
<div class="fixed bottom-0 left-0 w-full z-50 modal-slide-up">
  <div class="bg-surface-card border-t border-primary/30 rounded-t-2xl shadow-[0_-10px_40px_rgba(123,94,234,0.15)] p-[16px]">
    <div class="w-12 h-1.5 bg-outline-variant/50 rounded-full mx-auto mb-4"></div>
    <div class="flex gap-4 items-center mb-4">
      <div class="w-20 h-20 rounded-xl overflow-hidden border-2 border-secondary shrink-0 bg-surface-container-high flex items-center justify-center">
        ${selectedCard.image_path
          ? `<img src="${selectedCard.image_path}" alt="${selectedCard.name}" class="w-full h-full object-cover"/>`
          : `<span class="material-symbols-outlined text-[40px] text-outline fill-icon">person</span>`}
      </div>
      <div class="flex-1">
        <h2 class="font-headline-md text-headline-md text-secondary mb-1">${selectedCard.name}</h2>
        <p class="font-label-caps text-label-caps text-on-surface-variant uppercase">${(RARITY_COLORS[selectedCard.rarity] || {}).label || selectedCard.rarity}</p>
      </div>
    </div>
    <div class="space-y-2 mb-4">
      ${Object.entries(STAT_ICONS).map(([key, s]) => `
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-${s.color} fill-icon w-5 text-center">${s.icon}</span>
        <div class="flex-1 h-2 bg-surface rounded-full overflow-hidden">
          <div class="h-full progress-bar-fill rounded-full" style="width:${Math.min(100, selectedCard[key])}%"></div>
        </div>
        <span class="font-stat-numeric text-stat-numeric w-8 text-left">${selectedCard[key]}</span>
      </div>`).join('')}
    </div>
    <button data-action="confirm_card"
      class="w-full bg-primary-container text-on-primary-container font-button-label text-button-label uppercase py-3 rounded-lg shadow-[0_0_15px_rgba(123,94,234,0.4)] active:scale-95 transition-all">
      ✅ تایید و شروع نبرد
    </button>
  </div>
</div>` : '';

  return `
<div class="min-h-screen flex flex-col ${selectedCard ? 'pb-[250px]' : 'pb-20'}">
  <!-- Header -->
  <header class="fixed top-0 w-full z-50 bg-surface-dim/80 backdrop-blur-xl border-b border-white/10 flex items-center px-[16px] py-[8px] h-16">
    <button data-action="go_home" class="text-on-surface-variant hover:text-primary transition-colors p-2 rounded-full bg-surface-container-low/50 mr-2">
      <span class="material-symbols-outlined fill-icon">arrow_forward</span>
    </button>
    <h1 class="font-headline-sm text-headline-sm uppercase tracking-wider text-primary">کارت خودت رو انتخاب کن</h1>
  </header>

  <main class="pt-[72px] px-[16px] pt-[80px] flex flex-col gap-4">
    <!-- Rarity Filter -->
    <div class="flex gap-2 overflow-x-auto pb-2 no-scrollbar mt-2">
      ${rarityFilters.map(f => `
      <button data-action="filter_rarity" data-value="${f.key}"
        class="px-4 py-1.5 rounded-full font-button-label text-button-label whitespace-nowrap active:scale-95 transition-transform
               ${f.key === 'all' ? 'bg-primary-container text-on-primary-container' : 'bg-surface-container border border-outline/30 text-on-surface-variant hover:text-primary'}">
        ${f.label}
      </button>`).join('')}
    </div>

    <!-- Card Grid -->
    <div class="grid grid-cols-2 gap-[8px]">
      ${cardGrid}
    </div>
  </main>

  ${bottomSheet}
</div>`;
}
