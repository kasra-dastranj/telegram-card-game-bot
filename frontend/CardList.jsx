import React, { useEffect, useState } from 'react';

export default function CardList() {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ type: '', message: '' });

  const fetchCards = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/cards');
      const data = await res.json();
      if (data.success) {
        setCards(data.cards || []);
      } else {
        setStatus({ type: 'error', message: data.error || 'Failed to load cards.' });
      }
    } catch (err) {
      setStatus({ type: 'error', message: 'Network error while loading cards.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCards(); }, []);

  const deleteCard = async (card) => {
    if (!card || !card.id) return;
    try {
      const res = await fetch(`/api/cards/${card.id}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        setStatus({ type: 'success', message: '✅ Card and related files deleted successfully' });
        await fetchCards();
      } else {
        setStatus({ type: 'error', message: data.error || 'Failed to delete card.' });
      }
    } catch (err) {
      setStatus({ type: 'error', message: 'Network error while deleting card.' });
    }
  };

  return (
    <div className="space-y-4">
      {status.message && (
        <div className={status.type === 'success' ? 'text-green-600' : 'text-red-600'}>
          {status.message}
        </div>
      )}

      {loading ? (
        <div>Loading...</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white">
            <thead>
              <tr className="bg-gray-100">
                <th className="py-2 px-4 border-b text-left">Image</th>
                <th className="py-2 px-4 border-b text-left">Name</th>
                <th className="py-2 px-4 border-b text-left">Rarity</th>
                <th className="py-2 px-4 border-b text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {cards.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="py-2 px-4 border-b">
                    <img
                      src={`/card_images/${c.name.toLowerCase().replace(/ /g, '_')}.png`}
                      alt={c.name}
                      className="h-10 w-10 object-cover rounded"
                      onError={(e) => (e.currentTarget.src = 'https://via.placeholder.com/40?text=No+Image')}
                    />
                  </td>
                  <td className="py-2 px-4 border-b">{c.name}</td>
                  <td className="py-2 px-4 border-b">{c.rarity}</td>
                  <td className="py-2 px-4 border-b">
                    <button
                      onClick={() => deleteCard(c)}
                      className="bg-red-600 hover:bg-red-700 text-white text-sm px-3 py-1 rounded"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
