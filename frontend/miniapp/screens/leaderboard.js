// screens/leaderboard.js — جدول امتیازات

function renderLeaderboard(state) {
  const lb = state.leaderboard;
  const loading = state.loading;

  const periods = [
    { key: "weekly", label: "هفتگی" },
    { key: "monthly", label: "ماهانه" },
    { key: "all", label: "کل زمان" },
  ];

  const entriesHtml = () => {
    if (loading || !lb) {
      return `<div class="flex justify-center py-12">
        <div class="text-on-surface-variant font-body-md">در حال بارگذاری...</div>
      </div>`;
    }

    const entries = lb.entries || [];
    if (entries.length === 0) {
      return `<div class="text-center py-12 text-on-surface-variant font-body-md">هیچ رکوردی یافت نشد</div>`;
    }

    return entries.map((e, i) => {
      const isTop3 = i < 3;
      const rankColors = ["text-secondary", "text-outline", "text-tertiary"];
      const rankIcons = ["trophy", null, null];
      const isMe = lb.my_rank && e.rank === lb.my_rank;

      return `
<div class="flex items-center p-3 bg-surface-card rounded-xl border ${isTop3 ? ['border-secondary/30', 'border-outline/20', 'border-tertiary/20'][i] : 'border-white/5'} ${isMe ? 'border-primary/40' : ''}">
  <div class="w-10 flex justify-center items-center">
    ${rankIcons[i]
      ? `<span class="material-symbols-outlined ${rankColors[i]} text-3xl fill-icon drop-shadow-[0_0_8px_rgba(240,192,64,0.8)]">${rankIcons[i]}</span>`
      : `<span class="font-stat-numeric text-headline-md ${i < 3 ? rankColors[i] : 'text-on-surface-variant'}">${e.rank}</span>`}
  </div>
  <div class="w-10 h-10 rounded-full bg-surface-container border border-white/10 mx-3 shrink-0 flex items-center justify-center">
    <span class="material-symbols-outlined text-outline fill-icon">person</span>
  </div>
  <div class="flex flex-col flex-1 min-w-0">
    <span class="font-body-lg text-body-lg text-text-primary truncate ${isTop3 ? 'font-bold' : ''}">${e.first_name || e.username || 'کاربر'}</span>
    ${e.username ? `<span class="font-label-caps text-label-caps text-on-surface-variant">@${e.username}</span>` : ''}
  </div>
  <div class="mr-auto text-left">
    <span class="font-stat-numeric ${i === 0 ? 'text-headline-md text-secondary' : i === 1 ? 'text-headline-sm' : 'text-body-lg'} text-text-primary">${e.score.toLocaleString()}</span>
  </div>
</div>`;
    }).join('');
  };

  return `
<div class="min-h-screen flex flex-col pb-32">
  <!-- Header -->
  <header class="fixed top-0 left-0 w-full z-50 flex justify-between items-center px-[16px] h-16
                 bg-surface-dim/80 backdrop-blur-xl border-b border-white/10 text-primary font-headline-sm text-headline-sm">
    <div class="flex items-center gap-3">
      <button data-action="go_home" class="text-on-surface-variant hover:text-primary transition-colors active:scale-95">
        <span class="material-symbols-outlined">arrow_back</span>
      </button>
      <span class="font-headline-md text-headline-md font-bold text-primary tracking-wider uppercase">TELBATTLE</span>
    </div>
  </header>

  <main class="pt-24 px-[16px] flex flex-col gap-6">
    <!-- Title & Filters -->
    <section class="flex flex-col gap-4">
      <h1 class="font-headline-lg text-headline-lg text-primary drop-shadow-[0_0_10px_rgba(203,190,255,0.3)]">جدول امتیازات</h1>
      <div class="flex bg-surface-container-low p-1 rounded-lg border border-white/5 w-full">
        ${periods.map((p, i) => `
        <button data-action="filter_leaderboard" data-value="${p.key}"
          class="flex-1 py-2 text-center rounded-md transition-colors font-button-label text-button-label
                 ${i === 0 ? 'bg-primary-container text-on-primary-container shadow-[0_0_10px_rgba(123,94,234,0.2)]'
                           : 'text-on-surface-variant hover:bg-surface-container-high'}">
          ${p.label}
        </button>`).join('')}
      </div>
    </section>

    <!-- Leaderboard List -->
    <section class="flex flex-col gap-[4px] pb-20">
      ${entriesHtml()}
    </section>
  </main>

  <!-- My Rank Sticky -->
  ${lb && lb.my_rank ? `
  <div class="fixed bottom-20 left-0 w-full px-[16px] z-40">
    <div class="flex items-center p-4 bg-surface-container-highest/95 backdrop-blur-md rounded-xl border border-primary shadow-[0_0_20px_rgba(123,94,234,0.2)]">
      <div class="w-10 flex justify-center items-center">
        <span class="font-stat-numeric text-headline-md text-primary">${lb.my_rank}</span>
      </div>
      <div class="w-10 h-10 rounded-full bg-primary-container/20 border-2 border-primary mx-3 shrink-0 flex items-center justify-center">
        <span class="material-symbols-outlined text-primary fill-icon">person</span>
      </div>
      <div class="flex flex-col flex-1 min-w-0">
        <span class="font-body-lg text-body-lg text-primary font-bold truncate">شما</span>
      </div>
      <div class="mr-auto text-left">
        <span class="font-stat-numeric text-headline-sm text-text-primary">${lb.my_score ? lb.my_score.toLocaleString() : 0}</span>
      </div>
    </div>
  </div>` : ''}

  <!-- Bottom Nav -->
  <nav class="fixed bottom-0 left-0 w-full z-50 flex justify-around items-center px-4 pb-4 pt-2
              bg-surface-container-lowest/90 backdrop-blur-lg border-t border-white/5 shadow-[0_-4px_20px_rgba(123,94,234,0.15)] rounded-t-xl">
    <button data-action="go_home" class="flex flex-col items-center justify-center text-on-surface-variant/60 hover:text-primary active:scale-90 transition-all">
      <span class="material-symbols-outlined text-2xl mb-1">swords</span>
      <span class="font-label-caps text-label-caps">Arena</span>
    </button>
    <button class="flex flex-col items-center justify-center text-primary bg-primary-container/20 rounded-xl py-1 px-3 shadow-[0_0_10px_rgba(123,94,234,0.3)]">
      <span class="material-symbols-outlined text-2xl mb-1 fill-icon">leaderboard</span>
      <span class="font-label-caps text-label-caps font-bold">Rank</span>
    </button>
    <button data-action="go_profile" class="flex flex-col items-center justify-center text-on-surface-variant/60 hover:text-primary active:scale-90 transition-all">
      <span class="material-symbols-outlined text-2xl mb-1">person</span>
      <span class="font-label-caps text-label-caps">Profile</span>
    </button>
  </nav>
</div>`;
}
