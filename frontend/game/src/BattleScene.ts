import Phaser from "phaser";
import type { CardData, FightData, RoundData } from "./api";

type CardView = Phaser.GameObjects.Container;
export type ArenaVisual = string | { arena_id?: string; id?: string; version?: number | null; background_url?: string | null };

const ARENA_ASSETS = {
  city: "/miniapp-assets/arena-backgrounds/city.webp",
  desert: "/miniapp-assets/arena-backgrounds/desert.webp",
  ice: "/miniapp-assets/arena-backgrounds/ice.webp",
  forest: "/miniapp-assets/arena-backgrounds/forest.webp",
  silent_temple: "/miniapp-assets/arena-backgrounds/silent_temple.webp",
  null_zone: "/miniapp-assets/arena-backgrounds/null_zone.webp",
  power_arena: "/miniapp-assets/arena-backgrounds/power_arena.webp",
  speed_track: "/miniapp-assets/arena-backgrounds/speed_track.webp",
  thinking_room: "/miniapp-assets/arena-backgrounds/thinking_room.webp",
  stage: "/miniapp-assets/arena-backgrounds/stage.webp",
} as const;

type ArenaAssetId = keyof typeof ARENA_ASSETS;

export interface QuickResultVisual {
  outcome: "win" | "loss" | "tie";
  playerValue?: number;
  opponentValue?: number;
}

export class BattleScene extends Phaser.Scene {
  private backdrop!: Phaser.GameObjects.Graphics;
  private arenaBackdrop?: Phaser.GameObjects.Image;
  private parallaxLayer!: Phaser.GameObjects.Container;
  private playerView?: CardView;
  private aiView?: CardView;
  private beam?: Phaser.GameObjects.Rectangle;
  private resultOverlay?: Phaser.GameObjects.Container;
  private quickSignature = "";
  private activeArenaId = "city";
  private activeArenaKey = "arena-bg-city";
  private handCards: CardData[] = [];
  private handViews: CardView[] = [];
  private handUi: Phaser.GameObjects.GameObject[] = [];
  private handPage = 0;
  private dropZone?: Phaser.GameObjects.Zone;
  private dropRing?: Phaser.GameObjects.Arc;
  private dropHint?: Phaser.GameObjects.Text;
  private parallaxTargetX = 0;
  private parallaxTargetY = 0;

  constructor() {
    super("arena");
  }

  preload(): void {
    Object.entries(ARENA_ASSETS).forEach(([id, path]) => this.load.image(`arena-bg-${id}`, path));
  }

  create(): void {
    this.cameras.main.setBackgroundColor("#050912");
    this.backdrop = this.add.graphics();
    this.drawArena();
    this.setArena("city");
    this.createAtmosphere();
    this.createAmbientMotion();
    this.createDragInteractions();
    if (!this.reducedMotion()) {
      this.input.on("pointermove", (pointer: Phaser.Input.Pointer) => {
        this.parallaxTargetX = ((pointer.x / 720) - 0.5) * 14;
        this.parallaxTargetY = ((pointer.y / 1280) - 0.5) * 8;
      });
    }
  }

  update(): void {
    if (!this.parallaxLayer) return;
    this.parallaxLayer.x = Phaser.Math.Linear(this.parallaxLayer.x, this.parallaxTargetX, 0.035);
    this.parallaxLayer.y = Phaser.Math.Linear(this.parallaxLayer.y, this.parallaxTargetY, 0.035);
  }

  showIdle(arenaId = "city"): void {
    this.quickSignature = "";
    this.clearCards();
    this.setArena(arenaId);
    this.cameras.main.fadeIn(260, 7, 17, 14);
  }

  showCardHand(cards: CardData[], arenaId = "city", force = false): void {
    const resolvedArena = this.arenaIdentity(arenaId);
    const signature = `hand:${resolvedArena}:${cards.map((card) => card.card_id).join(",")}`;
    if (!force && signature === this.quickSignature && this.handViews.length) return;
    this.quickSignature = signature;
    this.clearCards();
    this.setArena(arenaId);
    this.handCards = cards;
    this.handPage = 0;
    this.renderHandPage();
  }

  resetCardHand(): void {
    if (!this.handCards.length) return;
    this.renderHandPage();
  }

  showBattle(fight: FightData): void {
    this.quickSignature = "";
    this.clearCards();
    this.setArena(fight.arena);
    const entries = [
      { key: `player-${fight.player_card.card_id}`, card: fight.player_card },
      { key: `ai-${fight.ai_card.card_id}`, card: fight.ai_card },
    ];
    this.withCardTextures(entries, () => this.placeCards(fight));
  }

  showQuickDuel(playerCard: CardData, opponentCard?: CardData, arenaId: ArenaVisual = "city"): void {
    const resolvedArena = this.arenaIdentity(arenaId);
    const signature = `duel:${resolvedArena}:${playerCard.card_id}:${opponentCard?.card_id || "hidden"}`;
    if (signature === this.quickSignature) return;
    this.quickSignature = signature;
    this.setArena(arenaId);
    const entries = [{ key: `quick-player-${playerCard.card_id}`, card: playerCard }];
    if (opponentCard) entries.push({ key: `quick-opponent-${opponentCard.card_id}`, card: opponentCard });
    this.withCardTextures(entries, () => {
      if (this.quickSignature !== signature) return;
      this.placeQuickCards(playerCard, opponentCard);
    });
  }

  showQuickResult(playerCard: CardData, opponentCard: CardData, visual: QuickResultVisual, arenaId: ArenaVisual = "city"): void {
    const resolvedArena = this.arenaIdentity(arenaId);
    const signature = `result:${resolvedArena}:${playerCard.card_id}:${opponentCard.card_id}:${visual.outcome}:${visual.playerValue}:${visual.opponentValue}`;
    if (signature === this.quickSignature) return;
    this.quickSignature = signature;
    this.setArena(arenaId);
    const entries = [
      { key: `quick-player-${playerCard.card_id}`, card: playerCard },
      { key: `quick-opponent-${opponentCard.card_id}`, card: opponentCard },
    ];
    this.withCardTextures(entries, () => {
      if (this.quickSignature !== signature) return;
      this.placeQuickCards(playerCard, opponentCard, true);
      this.animateQuickResult(visual);
    });
  }

  async animateRound(result: RoundData): Promise<void> {
    const playerWon = result.round_winner === "player";
    const color = result.round_winner === "tie" ? 0xf8c15a : playerWon ? 0x3ddc97 : 0xff5e6c;
    const fromX = playerWon ? 210 : 510;
    const toX = playerWon ? 510 : 210;
    this.beam?.destroy();
    this.beam = this.add.rectangle(fromX, 590, 18, 6, color, 0.9).setDepth(30);
    this.beam.setRotation(playerWon ? -0.22 : Math.PI + 0.22);
    await new Promise<void>((resolve) => {
      this.tweens.add({
        targets: this.beam,
        x: toX,
        scaleX: 16,
        alpha: 0,
        duration: 360,
        ease: "Expo.easeOut",
        onComplete: () => resolve(),
      });
      const target = playerWon ? this.aiView : this.playerView;
      if (target) {
        this.tweens.add({ targets: target, x: target.x + (playerWon ? 22 : -22), duration: 80, yoyo: true, repeat: 2 });
      }
    });
    this.createImpact(toX, 590, color);
    this.cameras.main.shake(150, 0.0035);
    this.cameras.main.flash(110, (color >> 16) & 255, (color >> 8) & 255, color & 255, true);
  }

  showVictory(won: boolean): void {
    const target = won ? this.playerView : this.aiView;
    if (!target) return;
    this.tweens.add({ targets: target, scale: 1.06, y: target.y - 16, duration: 520, ease: "Back.easeOut" });
  }

  private arenaIdentity(arena: ArenaVisual = "city"): string {
    if (typeof arena === "string") return arena.toLowerCase().replace("arenatype.", "") || "neutral";
    return `${arena.arena_id || arena.id || "neutral"}:v${arena.version ?? "legacy"}`;
  }

  private setArena(arena: ArenaVisual = "city"): void {
    const details = typeof arena === "string" ? { arena_id: arena } : arena;
    let id = String(details.arena_id || details.id || "neutral").toLowerCase().replace("arenatype.", "");
    if (id === "neon") id = "city"; // legacy demo identifier only
    const versionedKey = details.background_url ? `arena-bg-${id}-v${details.version ?? "asset"}` : `arena-bg-${id}`;
    this.activeArenaId = id;
    this.activeArenaKey = versionedKey;
    if (details.background_url && !this.textures.exists(versionedKey)) {
      if (!this.load.isLoading()) {
        this.load.once(Phaser.Loader.Events.COMPLETE, () => {
          if (this.activeArenaKey === versionedKey) this.setArena(details);
        });
        this.load.image(versionedKey, details.background_url);
        this.load.start();
      }
      this.showNeutralArena();
      return;
    }
    const texture = this.textures.exists(versionedKey)
      ? versionedKey
      : (id in ARENA_ASSETS && this.textures.exists(`arena-bg-${id}`) ? `arena-bg-${id}` : undefined);
    if (!texture) { this.showNeutralArena(); return; }
    this.arenaBackdrop?.destroy();
    // Keep the arena recognizable without competing with the card faces.
    const image = this.add.image(360, 640, texture).setDepth(1).setTint(0x829080);
    const scale = Math.max(720 / image.width, 1280 / image.height);
    image.setScale(scale);
    this.arenaBackdrop = image;
  }

  private showNeutralArena(): void {
    this.arenaBackdrop?.destroy();
    this.arenaBackdrop = undefined;
  }

  private createDragInteractions(): void {
    this.input.on(Phaser.Input.Events.DRAG_START, (_pointer: Phaser.Input.Pointer, gameObject: Phaser.GameObjects.GameObject) => {
      const card = gameObject.getData("hand-card") as CardData | undefined;
      if (!card) return;
      const view = gameObject as CardView;
      view.setDepth(50).setAngle(0);
      this.tweens.killTweensOf(view);
      this.tweens.add({ targets: view, scale: 0.62, duration: this.reducedMotion() ? 0 : 130, ease: "Quad.easeOut" });
      this.dropRing?.setStrokeStyle(7, this.rarityColor(card.rarity), 0.95).setAlpha(1);
      this.dropHint?.setText("رها کن تا انتخاب قفل شود").setAlpha(1);
      this.game.events.emit("card-drag-start", card.card_id);
    });

    this.input.on(Phaser.Input.Events.DRAG, (_pointer: Phaser.Input.Pointer, gameObject: Phaser.GameObjects.GameObject, dragX: number, dragY: number) => {
      if (!gameObject.getData("hand-card")) return;
      const view = gameObject as CardView;
      view.x = Phaser.Math.Clamp(dragX, 90, 630);
      view.y = Phaser.Math.Clamp(dragY, 220, 1120);
    });

    this.input.on(Phaser.Input.Events.DROP, (_pointer: Phaser.Input.Pointer, gameObject: Phaser.GameObjects.GameObject) => {
      const card = gameObject.getData("hand-card") as CardData | undefined;
      if (!card || gameObject.getData("drop-accepted")) return;
      const view = gameObject as CardView;
      view.setData("drop-accepted", true);
      this.handViews.forEach((item) => item.disableInteractive());
      this.dropHint?.setText("انتخاب نهایی شد");
      this.tweens.add({
        targets: view,
        x: 360,
        y: 650,
        angle: 0,
        scale: 0.67,
        duration: this.reducedMotion() ? 0 : 260,
        ease: "Back.easeOut",
        onComplete: () => {
          this.createImpact(360, 650, this.rarityColor(card.rarity));
          this.game.events.emit("card-dropped", card.card_id);
        },
      });
    });

    this.input.on(Phaser.Input.Events.DRAG_END, (_pointer: Phaser.Input.Pointer, gameObject: Phaser.GameObjects.GameObject, dropped: boolean) => {
      if (!gameObject.getData("hand-card") || dropped || gameObject.getData("drop-accepted")) return;
      const view = gameObject as CardView;
      this.dropRing?.setStrokeStyle(5, 0x76f5dc, 0.66).setAlpha(0.82);
      this.dropHint?.setText("کارت را بکش و داخل حلقه رها کن").setAlpha(0.88);
      this.tweens.add({
        targets: view,
        x: Number(view.getData("home-x")),
        y: Number(view.getData("home-y")),
        angle: Number(view.getData("home-angle")),
        scale: Number(view.getData("home-scale")),
        duration: this.reducedMotion() ? 0 : 230,
        ease: "Back.easeOut",
        onComplete: () => view.setDepth(Number(view.getData("home-depth"))),
      });
    });
  }

  private renderHandPage(): void {
    this.clearHandVisuals();
    if (!this.handCards.length) {
      this.handUi.push(this.add.text(360, 650, "کارتی برای نمایش پیدا نشد", { fontFamily: "Tahoma", fontSize: "24px", color: "#ffffff" }).setOrigin(0.5).setDepth(20));
      return;
    }

    const pageSize = 7;
    const pageCount = Math.max(1, Math.ceil(this.handCards.length / pageSize));
    this.handPage = Phaser.Math.Clamp(this.handPage, 0, pageCount - 1);
    const pageCards = this.handCards.slice(this.handPage * pageSize, (this.handPage + 1) * pageSize);
    const pageSignature = `${this.quickSignature}:page:${this.handPage}`;
    const entries = pageCards.map((card) => ({ key: `hand-${card.card_id}`, card }));
    this.withCardTextures(entries, () => {
      if (`${this.quickSignature}:page:${this.handPage}` !== pageSignature) return;
      this.clearHandVisuals();
      this.createDropTarget();
      const spacing = pageCards.length > 1 ? Math.min(92, 552 / (pageCards.length - 1)) : 0;
      pageCards.forEach((card, index) => {
        const offset = index - (pageCards.length - 1) / 2;
        const x = 360 + offset * spacing;
        const y = 1060 + Math.abs(offset) * 11;
        const angle = offset * 4.5;
        const scale = 0.42;
        const depth = 20 + index;
        const view = this.makeCard(card, `hand-${card.card_id}`, x, y, true)
          .setScale(scale)
          .setAngle(angle)
          .setDepth(depth)
          .setSize(286, 382)
          .setInteractive({ useHandCursor: true });
        view.setData({
          "hand-card": card,
          "home-x": x,
          "home-y": y,
          "home-angle": angle,
          "home-scale": scale,
          "home-depth": depth,
          "drop-accepted": false,
        });
        this.input.setDraggable(view);
        this.handViews.push(view);
      });

      if (pageCount > 1) {
        this.handUi.push(
          this.createHandPageButton(120, -1, this.handPage > 0),
          this.createHandPageButton(600, 1, this.handPage < pageCount - 1),
          this.add.text(360, 1222, `${this.handPage + 1} / ${pageCount}`, { fontFamily: "Segoe UI", fontSize: "17px", color: "#dffcf4", fontStyle: "bold" }).setOrigin(0.5).setDepth(35),
        );
      }
      this.game.events.emit("hand-page-changed", this.handPage + 1, pageCount);
    });
  }

  private createDropTarget(): void {
    this.dropZone = this.add.zone(360, 650, 236, 236).setRectangleDropZone(236, 236).setDepth(10);
    this.dropRing = this.add.circle(360, 650, 112, 0x08181d, 0.16).setStrokeStyle(5, 0x76f5dc, 0.66).setDepth(9);
    this.dropHint = this.add.text(360, 650, "کارت را بکش و داخل حلقه رها کن", {
      fontFamily: "Tahoma",
      fontSize: "19px",
      color: "#f4fffb",
      fontStyle: "bold",
      align: "center",
      wordWrap: { width: 184 },
      stroke: "#061018",
      strokeThickness: 5,
    }).setOrigin(0.5).setDepth(10).setAlpha(0.88);
    this.handUi.push(this.dropZone, this.dropRing, this.dropHint);
    if (!this.reducedMotion()) {
      this.tweens.add({ targets: this.dropRing, scale: 1.06, alpha: { from: 0.62, to: 0.92 }, duration: 1100, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
    }
  }

  private createHandPageButton(x: number, direction: -1 | 1, enabled: boolean): Phaser.GameObjects.Container {
    const circle = this.add.circle(0, 0, 28, 0x07131c, enabled ? 0.92 : 0.42).setStrokeStyle(2, 0x76f5dc, enabled ? 0.62 : 0.16);
    const label = this.add.text(0, -2, direction < 0 ? "‹" : "›", { fontFamily: "Segoe UI", fontSize: "38px", color: enabled ? "#76f5dc" : "#55636b", fontStyle: "bold" }).setOrigin(0.5);
    const button = this.add.container(x, 1140, [circle, label]).setDepth(38).setSize(60, 60);
    if (enabled) {
      button.setInteractive({ useHandCursor: true }).on("pointerup", () => {
        this.handPage += direction;
        this.renderHandPage();
      });
    }
    return button;
  }

  private clearHandVisuals(): void {
    this.handViews.forEach((view) => {
      this.tweens.killTweensOf(view);
      view.destroy(true);
    });
    this.handUi.forEach((item) => {
      this.tweens.killTweensOf(item);
      item.destroy();
    });
    this.handViews = [];
    this.handUi = [];
    this.dropZone = undefined;
    this.dropRing = undefined;
    this.dropHint = undefined;
  }

  private drawArena(): void {
    const g = this.backdrop;
    g.clear();
    g.fillGradientStyle(0x050912, 0x08131e, 0x11142a, 0x04060d, 1);
    g.fillRect(0, 0, 720, 1280);

    // Distant skyline and light shafts make the flat canvas read as a deep arena.
    g.fillStyle(0x0d1830, 0.9);
    g.fillTriangle(0, 500, 132, 286, 248, 500);
    g.fillTriangle(118, 500, 304, 335, 438, 500);
    g.fillTriangle(342, 500, 532, 268, 720, 500);
    g.fillStyle(0x152343, 0.42);
    g.fillTriangle(10, 520, 210, 360, 338, 520);
    g.fillTriangle(410, 520, 598, 350, 710, 520);
    g.fillGradientStyle(0x35d9ff, 0x765dff, 0x35d9ff, 0x765dff, 0.16);
    g.fillTriangle(110, 0, 235, 0, 350, 620);
    g.fillTriangle(505, 0, 610, 0, 370, 620);

    g.fillStyle(0x07101e, 0.96);
    g.fillRect(0, 492, 720, 788);
    g.lineStyle(2, 0x45e8d0, 0.09);
    for (let i = -6; i < 16; i += 1) {
      g.lineBetween(360, 545, i * 86, 1280);
    }
    const floorLines = [585, 640, 710, 798, 905, 1032, 1180];
    floorLines.forEach((y, index) => {
      g.lineStyle(index < 2 ? 2 : 1, index % 2 === 0 ? 0x45e8d0 : 0x796aff, 0.08 + index * 0.008);
      g.lineBetween(0, y, 720, y);
    });

    // Raised platform and luminous inlay.
    g.fillStyle(0x11182a, 0.98);
    g.fillEllipse(360, 586, 650, 230);
    g.fillStyle(0x050812, 0.86);
    g.fillEllipse(360, 594, 590, 178);
    g.lineStyle(12, 0x02040a, 0.72);
    g.strokeEllipse(360, 598, 620, 202);
    g.lineStyle(3, 0x45e8d0, 0.24);
    g.strokeEllipse(360, 584, 574, 164);
    g.lineStyle(2, 0xc39bff, 0.18);
    g.strokeEllipse(360, 584, 430, 112);

    // Foreground rails strengthen the perspective without extra bitmap weight.
    g.fillStyle(0x05070d, 0.9);
    g.fillTriangle(0, 1030, 92, 950, 62, 1280);
    g.fillTriangle(720, 1030, 628, 950, 658, 1280);
    g.lineStyle(3, 0x45e8d0, 0.14);
    g.lineBetween(62, 1280, 92, 950);
    g.lineBetween(658, 1280, 628, 950);
  }

  private createAtmosphere(): void {
    const objects: Phaser.GameObjects.GameObject[] = [];
    const cyanHaze = this.add.ellipse(175, 350, 420, 540, 0x2dcee8, 0.045).setBlendMode(Phaser.BlendModes.ADD);
    const violetHaze = this.add.ellipse(565, 285, 370, 500, 0x735cff, 0.055).setBlendMode(Phaser.BlendModes.ADD);
    const horizon = this.add.rectangle(360, 505, 680, 3, 0x75f8e3, 0.24).setBlendMode(Phaser.BlendModes.ADD);
    const halo = this.add.ellipse(360, 582, 530, 142, 0x48ebcf, 0.025)
      .setStrokeStyle(3, 0x48ebcf, 0.17)
      .setBlendMode(Phaser.BlendModes.ADD);
    objects.push(cyanHaze, violetHaze, horizon, halo);
    this.parallaxLayer = this.add.container(0, 0, objects).setDepth(2);
    if (!this.reducedMotion()) {
      this.tweens.add({ targets: cyanHaze, x: 220, alpha: { from: 0.025, to: 0.075 }, duration: 5200, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
      this.tweens.add({ targets: violetHaze, x: 520, alpha: { from: 0.03, to: 0.08 }, duration: 6100, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
      this.tweens.add({ targets: halo, scaleX: 1.08, scaleY: 1.12, alpha: { from: 0.34, to: 0.72 }, duration: 1900, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
    }
  }

  private createAmbientMotion(): void {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    for (let i = 0; i < 18; i += 1) {
      const color = i % 5 === 0 ? 0xe4ad4e : i % 2 === 0 ? 0x6d62ff : 0x45e8d0;
      const dot = this.add.circle(Phaser.Math.Between(26, 694), Phaser.Math.Between(80, 1160), Phaser.Math.Between(1, 3), color, Phaser.Math.FloatBetween(0.08, 0.24))
        .setDepth(3)
        .setBlendMode(Phaser.BlendModes.ADD);
      this.tweens.add({ targets: dot, y: dot.y - Phaser.Math.Between(40, 150), x: dot.x + Phaser.Math.Between(-18, 18), alpha: { from: dot.alpha, to: 0 }, duration: Phaser.Math.Between(2800, 5600), yoyo: true, repeat: -1, delay: Phaser.Math.Between(0, 1800), ease: "Sine.easeInOut" });
    }
  }

  private placeCards(fight: FightData): void {
    this.clearCards();
    // Preserve background_url and version while card textures finish loading.
    // Reducing this payload to arena_id replaces custom registry media.
    this.setArena(fight.arena);
    this.aiView = this.makeCard(fight.ai_card, `ai-${fight.ai_card.card_id}`, 360, 330, false);
    this.playerView = this.makeCard(fight.player_card, `player-${fight.player_card.card_id}`, 360, 760, true);
    if (this.reducedMotion()) {
      this.aiView.setScale(0.62).setAngle(2);
      this.playerView.setScale(0.74).setAngle(-2);
      return;
    }
    this.aiView.setAlpha(0).setY(255).setScale(0.44).setAngle(8);
    this.playerView.setAlpha(0).setY(860).setScale(0.48).setAngle(-8);
    this.tweens.add({ targets: this.aiView, alpha: 1, y: 330, scale: 0.62, angle: 2, duration: 520, ease: "Back.easeOut" });
    this.tweens.add({ targets: this.playerView, alpha: 1, y: 760, scale: 0.74, angle: -2, duration: 520, delay: 90, ease: "Back.easeOut", onComplete: () => this.floatCard(this.playerView, 1) });
    this.floatCard(this.aiView, -1, 560);
  }

  private placeQuickCards(playerCard: CardData, opponentCard?: CardData, immediate = false): void {
    this.clearCards();
    this.playerView = this.makeCard(playerCard, `quick-player-${playerCard.card_id}`, 360, 760, true).setScale(0.66);
    this.aiView = opponentCard
      ? this.makeCard(opponentCard, `quick-opponent-${opponentCard.card_id}`, 360, 330, false).setScale(0.54)
      : this.makeHiddenCard(360, 330).setScale(0.54);
    this.playerView.setAngle(-2.4);
    this.aiView.setAngle(2.4);
    if (immediate || this.reducedMotion()) return;
    this.playerView.setAlpha(0).setY(875).setScale(0.48).setAngle(-11);
    this.aiView.setAlpha(0).setY(220).setScale(0.4).setAngle(11);
    this.tweens.add({ targets: this.playerView, alpha: 1, y: 760, scale: 0.66, angle: -2.4, duration: 480, ease: "Back.easeOut", onComplete: () => this.floatCard(this.playerView, 1) });
    this.tweens.add({ targets: this.aiView, alpha: 1, y: 330, scale: 0.54, angle: 2.4, duration: 480, delay: 70, ease: "Back.easeOut", onComplete: () => this.floatCard(this.aiView, -1) });
  }

  private makeHiddenCard(x: number, y: number): CardView {
    const objects: Phaser.GameObjects.GameObject[] = [];
    const floorShadow = this.add.ellipse(8, 220, 252, 44, 0x000000, 0.58);
    const glow = this.add.rectangle(5, 6, 302, 400, 0xe4ad4e, 0.04).setStrokeStyle(13, 0xe4ad4e, 0.07).setBlendMode(Phaser.BlendModes.ADD);
    const backPlate = this.add.rectangle(8, 10, 288, 384, 0x01040a, 0.9).setStrokeStyle(2, 0x5d667c, 0.34);
    const frame = this.add.rectangle(0, 0, 286, 382, 0x091522, 0.98).setStrokeStyle(4, 0xe4ad4e, 0.76);
    const inner = this.add.rectangle(0, -22, 238, 272, 0x0d2130, 1).setStrokeStyle(2, 0x45e8d0, 0.3);
    const pattern = this.add.graphics().lineStyle(3, 0x45e8d0, 0.12);
    for (let offset = -130; offset <= 90; offset += 32) {
      pattern.lineBetween(-116, offset, 116, offset + 90);
    }
    objects.push(floorShadow, glow, backPlate, frame, inner, pattern);
    objects.push(
      this.add.circle(0, -22, 58, 0x07110e, 0.92).setStrokeStyle(3, 0xe4ad4e, 0.55),
      this.add.text(0, -22, "?", { fontFamily: "Segoe UI", fontSize: "44px", color: "#e4ad4e", fontStyle: "bold" }).setOrigin(0.5),
      this.add.rectangle(0, 131, 270, 96, 0x07110e, 0.96),
      this.add.text(0, 112, "انتخاب مخفی", { fontFamily: "Tahoma", fontSize: "23px", color: "#ffffff", fontStyle: "bold" }).setOrigin(0.5),
      this.add.text(0, 147, "تا پایان تصمیم‌گیری", { fontFamily: "Tahoma", fontSize: "16px", color: "#d7bd87" }).setOrigin(0.5),
    );
    const container = this.add.container(x, y, objects).setDepth(12);
    if (!this.reducedMotion()) this.tweens.add({ targets: glow, alpha: { from: 0.18, to: 0.5 }, duration: 1450, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
    return container;
  }

  private animateQuickResult(visual: QuickResultVisual): void {
    if (!this.playerView || !this.aiView) return;
    const playerWon = visual.outcome === "win";
    const tie = visual.outcome === "tie";
    const winner = tie ? undefined : playerWon ? this.playerView : this.aiView;
    const loser = tie ? undefined : playerWon ? this.aiView : this.playerView;
    const color = tie ? 0xe4ad4e : playerWon ? 0x2ce6a3 : 0xff5e6c;
    const scoreObjects: Phaser.GameObjects.GameObject[] = window.innerHeight >= 720 ? [
      this.add.rectangle(220, 610, 148, 54, 0x07110e, 0.94).setStrokeStyle(2, playerWon || tie ? 0x2ce6a3 : 0xff5e6c, 0.7),
      this.add.text(220, 610, String(visual.playerValue ?? "—"), { fontFamily: "Segoe UI", fontSize: "28px", color: "#ffffff", fontStyle: "bold" }).setOrigin(0.5),
      this.add.rectangle(500, 610, 148, 54, 0x07110e, 0.94).setStrokeStyle(2, !playerWon || tie ? 0xe4ad4e : 0xff5e6c, 0.7),
      this.add.text(500, 610, String(visual.opponentValue ?? "—"), { fontFamily: "Segoe UI", fontSize: "28px", color: "#ffffff", fontStyle: "bold" }).setOrigin(0.5),
    ] : [];
    this.resultOverlay = this.add.container(0, 0, scoreObjects).setDepth(24);
    if (this.reducedMotion()) {
      loser?.setAlpha(0.5);
      if (winner) winner.setScale(winner.scaleX + 0.05);
      return;
    }
    this.resultOverlay.setAlpha(0);
    this.tweens.add({ targets: this.resultOverlay, alpha: 1, y: -8, duration: 240, ease: "Quad.easeOut" });
    if (tie) {
      this.tweens.add({ targets: this.playerView, scale: this.playerView.scaleX + 0.04, duration: 260, yoyo: true, ease: "Sine.easeInOut" });
      this.tweens.add({ targets: this.aiView, scale: this.aiView.scaleX + 0.04, duration: 260, yoyo: true, ease: "Sine.easeInOut" });
    } else {
      const targetY = playerWon ? 330 : 760;
      const startY = playerWon ? 760 : 330;
      loser?.setAlpha(0.42);
      this.tweens.add({ targets: loser, angle: playerWon ? 8 : -8, x: 378, duration: 340, ease: "Quad.easeOut" });
      this.tweens.add({ targets: winner, scale: playerWon ? 0.72 : 0.6, angle: 0, duration: 460, ease: "Back.easeOut" });
      const beamGlow = this.add.rectangle(360, startY, 24, 24, color, 0.22).setDepth(29).setBlendMode(Phaser.BlendModes.ADD);
      this.beam = this.add.rectangle(360, startY, 7, 18, color, 0.9).setDepth(30);
      this.tweens.add({ targets: beamGlow, y: targetY, scaleY: 20, alpha: 0, duration: 430, ease: "Expo.easeOut", onComplete: () => beamGlow.destroy() });
      this.tweens.add({ targets: this.beam, y: targetY, scaleY: 18, alpha: 0, duration: 380, ease: "Expo.easeOut" });
      this.time.delayedCall(250, () => this.createImpact(360, targetY, color));
    }
    this.cameras.main.shake(170, tie ? 0.002 : 0.0045);
    this.cameras.main.flash(120, (color >> 16) & 255, (color >> 8) & 255, color & 255, true);
  }

  private withCardTextures(entries: Array<{ key: string; card: CardData }>, ready: () => void): void {
    const missing = entries.filter(({ key, card }) => card.image_url && !this.textures.exists(key));
    if (!missing.length) {
      ready();
      return;
    }
    missing.forEach(({ key, card }) => this.load.image(key, card.image_url));
    this.load.once(Phaser.Loader.Events.COMPLETE, ready);
    this.load.start();
  }

  private reducedMotion(): boolean {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  private makeCard(card: CardData, texture: string, x: number, y: number, player: boolean): CardView {
    const rarityColor = this.rarityColor(card.rarity);
    const rarityLabel = card.rarity.toUpperCase();
    const strongest = this.strongestStat(card);
    const floorShadow = this.add.ellipse(9, 222, 260, 48, 0x000000, 0.62);
    const aura = this.add.ellipse(0, -18, 320, 370, rarityColor, 0.035)
      .setStrokeStyle(10, rarityColor, 0.08)
      .setBlendMode(Phaser.BlendModes.ADD);
    const backPlate = this.add.rectangle(9, 11, 288, 384, 0x02050c, 0.94).setStrokeStyle(2, 0x8390a6, 0.22);
    const frame = this.add.rectangle(0, 0, 286, 382, 0x0a111d, 0.99).setStrokeStyle(4, rarityColor, 0.94);
    const innerFrame = this.add.rectangle(0, -42, 260, 278, 0x07101b, 1).setStrokeStyle(2, rarityColor, 0.28);
    const topAccent = this.add.rectangle(0, -184, 176, 4, rarityColor, 0.94).setBlendMode(Phaser.BlendModes.ADD);
    const objects: Phaser.GameObjects.GameObject[] = [floorShadow, aura, backPlate, frame, innerFrame, topAccent];
    if (card.image_url && this.textures.exists(texture)) {
      const image = this.add.image(0, -42, texture);
      const scale = Math.max(256 / image.width, 270 / image.height);
      const cropWidth = 256 / scale;
      const cropHeight = 270 / scale;
      image.setCrop(
        Math.max(0, (image.width - cropWidth) / 2),
        Math.max(0, (image.height - cropHeight) / 2),
        Math.min(image.width, cropWidth),
        Math.min(image.height, cropHeight),
      );
      image.setScale(scale);
      objects.push(image);
    } else {
      objects.push(this.add.text(0, -42, card.name.slice(0, 1), { fontFamily: "Tahoma", fontSize: "88px", color: "#dfeee8" }).setOrigin(0.5));
    }
    const sheen = this.add.rectangle(-128, -32, 48, 350, 0xffffff, 0.055)
      .setAngle(-20)
      .setBlendMode(Phaser.BlendModes.ADD);
    objects.push(
      sheen,
      this.add.rectangle(0, 132, 270, 102, 0x050a12, 0.96).setStrokeStyle(1, rarityColor, 0.22),
      this.add.rectangle(-83, -168, 94, 25, rarityColor, 0.17).setStrokeStyle(1, rarityColor, 0.72),
      this.add.text(-83, -168, rarityLabel, { fontFamily: "Segoe UI", fontSize: "11px", color: Phaser.Display.Color.IntegerToColor(rarityColor).rgba, fontStyle: "bold" }).setOrigin(0.5),
      this.add.text(0, 104, card.name, { fontFamily: "Vazirmatn, Tahoma", fontSize: "24px", color: "#fff1d5", fontStyle: "bold", align: "center" }).setOrigin(0.5),
      this.add.text(0, 139, player ? "کارت شما" : "حریف", { fontFamily: "Vazirmatn, Tahoma", fontSize: "18px", color: player ? "#d8c697" : "#e3a59a" }).setOrigin(0.5),
      this.add.rectangle(0, 171, 226, 24, 0x111a29, 0.96).setStrokeStyle(1, rarityColor, 0.26),
      this.add.text(0, 171, `${strongest.label}  ${strongest.value}`, { fontFamily: "Vazirmatn, Tahoma", fontSize: "18px", color: "#e4d7b8", fontStyle: "bold" }).setOrigin(0.5),
    );
    const container = this.add.container(x, y, objects).setDepth(12);
    if (!this.reducedMotion()) {
      this.tweens.add({ targets: aura, scaleX: 1.08, scaleY: 1.04, alpha: { from: 0.34, to: 0.78 }, duration: card.rarity === "legend" ? 1200 : 1750, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
      this.tweens.add({ targets: sheen, x: 220, alpha: { from: 0, to: 0.13 }, duration: 1150, delay: 420, hold: 1800, repeatDelay: 1500, repeat: -1, ease: "Sine.easeInOut" });
    }
    return container;
  }

  private rarityColor(rarity: string): number {
    if (rarity === "legend") return 0xd5b773;
    if (rarity === "epic") return 0xb49ac5;
    if (rarity === "rare") return 0x8caec4;
    return 0x9ba794;
  }

  private strongestStat(card: CardData): { label: string; value: number } {
    const stats = [
      { label: "قدرت", value: card.power },
      { label: "سرعت", value: card.speed },
      { label: "هوش", value: card.iq },
      { label: "محبوبیت", value: card.popularity },
    ];
    return stats.reduce((best, item) => item.value > best.value ? item : best, stats[0]);
  }

  private floatCard(view: CardView | undefined, direction: number, delay = 0): void {
    if (!view || this.reducedMotion()) return;
    this.tweens.add({
      targets: view,
      y: view.y - 7,
      angle: view.angle + direction * 0.8,
      duration: 1900,
      delay,
      yoyo: true,
      repeat: -1,
      ease: "Sine.easeInOut",
    });
  }

  private createImpact(x: number, y: number, color: number): void {
    if (this.reducedMotion()) return;
    const ring = this.add.circle(x, y, 18, color, 0).setStrokeStyle(5, color, 0.9).setDepth(31).setBlendMode(Phaser.BlendModes.ADD);
    this.tweens.add({ targets: ring, scale: 5.5, alpha: 0, duration: 430, ease: "Expo.easeOut", onComplete: () => ring.destroy() });
    for (let i = 0; i < 12; i += 1) {
      const spark = this.add.circle(x, y, Phaser.Math.Between(2, 4), color, 0.9).setDepth(32).setBlendMode(Phaser.BlendModes.ADD);
      const angle = Phaser.Math.FloatBetween(0, Math.PI * 2);
      const distance = Phaser.Math.Between(52, 130);
      this.tweens.add({ targets: spark, x: x + Math.cos(angle) * distance, y: y + Math.sin(angle) * distance, scale: 0.2, alpha: 0, duration: Phaser.Math.Between(280, 520), ease: "Quad.easeOut", onComplete: () => spark.destroy() });
    }
  }

  private clearCards(): void {
    this.clearHandVisuals();
    this.handCards = [];
    this.resultOverlay?.destroy(true);
    this.resultOverlay = undefined;
    this.beam?.destroy();
    this.beam = undefined;
    this.playerView?.destroy(true);
    this.aiView?.destroy(true);
    this.playerView = undefined;
    this.aiView = undefined;
  }
}
