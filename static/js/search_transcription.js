// Search functionality for transcriptions
let searchTimeout;
let currentMeetingIdForSearch = null;

// Initialize search when modal opens
function initTranscriptionSearch(meetingId) {
    currentMeetingIdForSearch = meetingId;
    const searchInput = document.getElementById('transcriptSearch');

    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchInTranscriptions(this.value);
            }, 300); // Debounce 300ms
        });
    }
}

// Perform search
function searchInTranscriptions(query) {
    const transcriptions = document.querySelectorAll('.transcription-item');
    const searchResults = document.getElementById('searchResults');

    if (!query || query.trim() === '') {
        // Show all and remove highlights
        transcriptions.forEach(item => {
            item.style.display = '';
            const textEl = item.querySelector('.transcription-text');
            if (textEl && textEl.hasAttribute('data-original')) {
                textEl.innerHTML = textEl.getAttribute('data-original');
            }
        });
        if (searchResults) searchResults.textContent = '';
        return;
    }

    const lowerQuery = query.toLowerCase();
    let foundCount = 0;

    transcriptions.forEach(item => {
        const text = item.getAttribute('data-text') || '';
        const textEl = item.querySelector('.transcription-text');

        if (text.includes(lowerQuery)) {
            item.style.display = '';
            foundCount++;

            // Store original if not already stored
            if (textEl && !textEl.hasAttribute('data-original')) {
                textEl.setAttribute('data-original', textEl.innerHTML);
            }

            // Highlight matching text
            const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
            const originalText = textEl.getAttribute('data-original') || textEl.textContent;
            const highlightedText = originalText.replace(regex, '<mark class="bg-warning text-dark">$1</mark>');
            textEl.innerHTML = highlightedText;
        } else {
            item.style.display = 'none';
        }
    });

    if (searchResults) {
        searchResults.innerHTML = `<span class="badge bg-info">${foundCount} ผลลัพธ์</span>`;
    }
}

// Clear search
function clearTranscriptSearch() {
    const searchInput = document.getElementById('transcriptSearch');
    if (searchInput) {
        searchInput.value = '';
        searchInTranscriptions('');
    }
}

// Escape special regex characters
function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Call this after loading transcriptions in modal
window.initTranscriptionSearch = initTranscriptionSearch;
window.searchInTranscriptions = searchInTranscriptions;
window.clearTranscriptSearch = clearTranscriptSearch;
