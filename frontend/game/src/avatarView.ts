import type { AvatarAppearance } from './api';

const escape = (value: string) => value.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));

export function avatarLayers(value: AvatarAppearance): string {
  const { face, frame, background } = value;
  const image = (url: string, cls: string, extra = '') => url ? `<img class="${cls}" src="${escape(url)}" alt="" ${extra}>` : '';
  if (face.kind === 'legacy') return `<div class="layered-avatar is-legacy" role="img" aria-label="${escape(face.name)}">${image(face.image_url,'avatar-legacy')}</div>`;
  const mask = frame.mask?.image_url;
  const style = mask ? `mask-image:url('${escape(mask)}');-webkit-mask-image:url('${escape(mask)}')` : 'border-radius:50%';
  return `<div class="layered-avatar" role="img" aria-label="آواتار ${escape(face.name)}">
    <div class="avatar-clipped" style="${style}"><div class="avatar-bg" style="background:${escape(background.color || '#8c3045')}"></div>${image(background.image_url,'avatar-bg')}
    ${!face.image_url ? '<span class="avatar-head-fallback">●</span>' : ''}${image(face.image_url,'avatar-head',`style="width:${100*face.scale}%;height:${100*face.scale}%;left:${50+100*face.offset_x}%;top:${50+100*face.offset_y}%"`)}</div>
    ${image(frame.image_url,'avatar-frame')}</div>`;
}
