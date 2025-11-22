import React, { useState } from 'react';

export default function CardUpload() {
  const [cardName, setCardName] = useState('');

  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [imageStatus, setImageStatus] = useState({ type: '', message: '' });

  const [stickerFile, setStickerFile] = useState(null);
  const [stickerStatus, setStickerStatus] = useState({ type: '', message: '' });
  const [stickerBadge, setStickerBadge] = useState(false);

  const onPickImage = (e) => {
    const file = e.target.files?.[0];
    setImageStatus({ type: '', message: '' });
    if (!file) return;
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setImagePreview(ev.target?.result);
    reader.readAsDataURL(file);
  };

  const onPickSticker = (e) => {
    const file = e.target.files?.[0];
    setStickerStatus({ type: '', message: '' });
    setStickerBadge(false);
    if (!file) return;
    setStickerFile(file);
  };

  const uploadImage = async () => {
    if (!imageFile) {
      setImageStatus({ type: 'error', message: 'Please choose a PNG or JPG image.' });
      return;
    }
    if (!cardName.trim()) {
      setImageStatus({ type: 'error', message: 'Please enter a card name.' });
      return;
    }

    const fd = new FormData();
    fd.append('image', imageFile);
    fd.append('card_name', cardName.trim());

    try {
      const res = await fetch('/api/upload_image', { method: 'POST', body: fd });
      const data = await res.json();
      if (data.success) {
        setImageStatus({ type: 'success', message: 'Image uploaded successfully.' });
      } else {
        setImageStatus({ type: 'error', message: data.error || 'Upload failed.' });
      }
    } catch (err) {
      setImageStatus({ type: 'error', message: 'Network error while uploading image.' });
    }
  };

  const uploadSticker = async () => {
    if (!stickerFile) {
      setStickerStatus({ type: 'error', message: 'Please choose a WebP sticker.' });
      return;
    }
    if (!cardName.trim()) {
      setStickerStatus({ type: 'error', message: 'Please enter a card name.' });
      return;
    }

    const fd = new FormData();
    fd.append('sticker', stickerFile);
    fd.append('card_name', cardName.trim());

    try {
      const res = await fetch('/api/upload_sticker', { method: 'POST', body: fd });
      const data = await res.json();
      if (data.success) {
        setStickerStatus({ type: 'success', message: 'WebP sticker uploaded successfully.' });
        setStickerBadge(true);
      } else {
        setStickerStatus({ type: 'error', message: data.error || 'Upload failed.' });
        setStickerBadge(false);
      }
    } catch (err) {
      setStickerStatus({ type: 'error', message: 'Network error while uploading sticker.' });
      setStickerBadge(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <label className="block text-gray-800 font-medium">Card name</label>
        <input
          type="text"
          value={cardName}
          onChange={(e) => setCardName(e.target.value)}
          placeholder="e.g., Iron Warrior"
          className="w-full p-2 border rounded"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* PNG/JPG image upload */}
        <div className="p-4 border rounded bg-white">
          <h3 className="font-semibold mb-2">PNG/JPG Card Image</h3>
          <p className="text-sm text-gray-600 mb-3">Used for web previews. Accepted formats: PNG, JPG.</p>

          <div className="relative">
            {imagePreview && (
              <div className="inline-block relative">
                <img src={imagePreview} alt="Preview" className="w-40 h-40 object-contain rounded border" />
                {stickerBadge && (
                  <span className="absolute -top-2 -right-2 bg-purple-600 text-white text-xs px-2 py-1 rounded-full shadow">
                    🎭 WebP Sticker
                  </span>
                )}
              </div>
            )}
          </div>

          <input type="file" accept="image/png,image/jpeg" onChange={onPickImage} className="mt-3" />
          <div className="mt-3 flex gap-2">
            <button onClick={uploadImage} className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded">
              Upload Image
            </button>
          </div>
          {imageStatus.message && (
            <p className={imageStatus.type === 'success' ? 'text-green-600 mt-2' : 'text-red-600 mt-2'}>
              {imageStatus.message}
            </p>
          )}
        </div>

        {/* WebP sticker upload */}
        <div className="p-4 border rounded bg-white">
          <h3 className="font-semibold mb-2">WebP Sticker</h3>
          <p className="text-sm text-gray-600 mb-1">Used by the Telegram bot.</p>
          <p className="text-sm text-gray-700 mb-3">Recommended size: 512×512px, max 500KB.</p>

          <input type="file" accept="image/webp" onChange={onPickSticker} />
          <div className="mt-3 flex gap-2">
            <button onClick={uploadSticker} className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded">
              Upload Sticker
            </button>
          </div>
          {stickerStatus.message && (
            <p className={stickerStatus.type === 'success' ? 'text-green-600 mt-2' : 'text-red-600 mt-2'}>
              {stickerStatus.message}
            </p>
          )}
        </div>
      </div>

      <div className="p-4 rounded bg-yellow-50 border border-yellow-200 text-sm text-gray-700">
        Tip: Need to convert PNG/JPG to WebP? Use ezgif.com: 
        <a className="text-blue-600 underline" href="https://ezgif.com/png-to-webp" target="_blank" rel="noreferrer">
          https://ezgif.com/png-to-webp
        </a>
      </div>
    </div>
  );
}
