// Wait until the HTML document is fully loaded before running the script
document.addEventListener('DOMContentLoaded', () => {

    // --- Helper Function to display messages ---
    const showMessage = (message, type) => {
        const container = document.getElementById('message-container');
        if (container) {
            container.textContent = message;
            container.className = `message ${type}`; // e.g., 'message success' or 'message error'
        }
    };

    // --- Authentication Logic (Login/Register) ---
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = loginForm.username.value;
            const password = loginForm.password.value;
            
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const result = await response.json();
            if (response.ok) {
                window.location.href = '/dashboard'; // Redirect on success
            } else {
                showMessage(result.error, 'error');
            }
        });
    }

    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = registerForm.username.value;
            const password = registerForm.password.value;

            const response = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            const result = await response.json();
            if (response.ok) {
                showMessage(result.message, 'success');
                setTimeout(() => window.location.href = '/login', 2000); // Redirect to login after 2s
            } else {
                showMessage(result.error, 'error');
            }
        });
    }

    // --- Logout Button ---
    const logoutBtn = document.getElementById('logout-btn');
    if(logoutBtn) {
        logoutBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            await fetch('/api/logout', { method: 'POST' });
            window.location.href = '/login';
        });
    }

    // --- Account Page Logic ---
    const tokenForm = document.getElementById('token-form');
    if (tokenForm) {
        tokenForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const token = document.getElementById('token-input').value;
            
            const response = await fetch('/api/update_token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token })
            });
            
            const result = await response.json();
            if(response.ok) {
                showMessage(result.message, 'success');
            } else {
                showMessage(result.error, 'error');
            }
        });
    }

    // --- Dashboard Analysis Logic ---
    const analyzeBtn = document.getElementById('analyze-btn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', async () => {
            const keywordInput = document.getElementById('keyword-input');
            const keyword = keywordInput.value.trim();
            if (!keyword) {
                alert('Please enter a keyword.');
                return;
            }

            const loader = document.getElementById('loader');
            const resultsContainer = document.getElementById('results-container');
            
            loader.classList.remove('hidden');
            resultsContainer.innerHTML = '';
            analyzeBtn.disabled = true;

            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ keyword })
                });

                const data = await response.json();
                
                if (response.ok) {
                    displayResults(data);
                } else {
                    resultsContainer.innerHTML = `<div class="card"><p class="message error">${data.error}</p></div>`;
                }

            } catch (error) {
                resultsContainer.innerHTML = `<div class="card"><p class="message error">An unexpected error occurred. Please try again.</p></div>`;
            } finally {
                loader.classList.add('hidden');
                analyzeBtn.disabled = false;
            }
        });
    }
    
    // --- Function to Render Results on Dashboard ---
    const displayResults = (data) => {
        const resultsContainer = document.getElementById('results-container');
        
        let relatedTopicsHtml = '<li>No related topics found.</li>';
        if(data.related_topics && data.related_topics.length > 0) {
            relatedTopicsHtml = data.related_topics.slice(0, 5).map(topic => 
                `<li>${topic.topic.title} (${topic.topic.type})</li>`
            ).join('');
        }

        let relatedQueriesHtml = '<li>No related queries found.</li>';
        if(data.related_queries && data.related_queries.length > 0) {
            relatedQueriesHtml = data.related_queries.slice(0, 7).map(q => 
                `<li>${q.query} ${q.rising ? '<span style="color: #1a73e8; font-weight: bold;">(Rising!)</span>' : ''}</li>`
            ).join('');
        }
        
        // Use marked.js library to convert AI's markdown response into HTML
        const aiRecommendationHtml = marked.parse(data.ai_recommendation || 'No recommendation available.');

        resultsContainer.innerHTML = `
            <div class="card">
                <h2>Analysis for "${data.keyword || 'your keyword'}"</h2>
                <p><strong>Trend Forecast:</strong> ${data.trend_data.trend} (${data.trend_data.reason})</p>
            </div>
            
            <div class="card">
                <h3>🤖 AI-Powered Strategy</h3>
                ${aiRecommendationHtml}
            </div>
            
            <div class="card">
                <h3>Related Topics</h3>
                <ul>${relatedTopicsHtml}</ul>
            </div>
            
            <div class="card">
                <h3>Related Queries</h3>
                <ul>${relatedQueriesHtml}</ul>
            </div>
        `;
    };
});
