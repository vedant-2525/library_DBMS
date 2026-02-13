document.addEventListener('DOMContentLoaded', () => {
    
    // --- 1. LIVE SEARCH LOGIC ---
    const searchInput = document.querySelector('input[placeholder="Search by title, author, or ISBN..."]');
    
    if (searchInput) {
        // Find the "Search" button explicitly by ID or relative position
        const searchBtn = document.getElementById('btn-search');
        const searchContainer = searchInput.parentElement;
        
        // Create Dropdown
        const dropdown = document.createElement('div');
        dropdown.className = 'search-dropdown';
        searchContainer.appendChild(dropdown);

        let debounceTimer;

        // A. Handle Typing
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            clearTimeout(debounceTimer);
            if (query.length === 0) {
                dropdown.style.display = 'none';
                return;
            }
            debounceTimer = setTimeout(() => fetchBooks(query), 300);
        });

        // B. Handle Search Button Click
        if (searchBtn) {
            searchBtn.addEventListener('click', (e) => {
                // If button is clicked, trigger the same search logic
                const query = searchInput.value.trim();
                if (query) {
                    fetchBooks(query);
                } else {
                    searchInput.focus();
                }
            });
        }

        async function fetchBooks(query) {
            try {
                dropdown.innerHTML = '<div class="p-3 text-sm text-gray-400">Searching...</div>';
                dropdown.style.display = 'block';

                const response = await fetch(`/api/books?q=${encodeURIComponent(query)}`);
                if (!response.ok) throw new Error("Network response was not ok");
                
                const books = await response.json();
                renderDropdown(books);
            } catch (error) {
                console.error('Search failed:', error);
                dropdown.innerHTML = '<div class="p-3 text-sm text-red-400">Error fetching data</div>';
            }
        }

        function renderDropdown(books) {
            dropdown.innerHTML = ''; 
            if (books.length === 0) {
                dropdown.innerHTML = '<div class="p-3 text-sm text-gray-400">No results found</div>';
                return;
            }
            books.forEach(book => {
                const div = document.createElement('div');
                div.className = 'search-item';
                div.innerHTML = `
                    <div class="font-medium text-sm text-gray-800">${book.title}</div>
                    <div class="text-xs text-gray-500">Book ID: ${book.book_id} | ISBN: ${book.isbn || 'N/A'}</div>
                `;
                div.addEventListener('click', () => {
                    searchInput.value = book.title; 
                    dropdown.style.display = 'none';
                });
                dropdown.appendChild(div);
            });
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!searchContainer.contains(e.target) && e.target !== searchBtn) {
                dropdown.style.display = 'none';
            }
        });
    }
});

// --- 2. TOAST SYSTEM (Used by Flask) ---
// This function needs to be global so the HTML script tag can call it
window.showToast = function(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? '<i class="fa-solid fa-check-circle text-emerald-500"></i>' 
                                    : '<i class="fa-solid fa-circle-exclamation text-red-500"></i>';

    toast.innerHTML = `${icon}<p class="text-sm font-medium text-gray-700">${message}</p>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease-out forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}