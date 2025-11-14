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

            if (response.ok) {
                window.location.href = '/';
            } else {
                const result = await response.json();
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
                setTimeout(() => window.location.href = '/login', 2000);
            } else {
                showMessage(result.error, 'error');
            }
        });
    }

    // --- Logout Button ---
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener("click", (e) => {
            e.preventDefault();
            const confirmBox = document.createElement("div");
            confirmBox.classList.add("confirm-modal");
            confirmBox.innerHTML = `
                <div class="confirm-content">
                    <p>Are you sure you want to logout?</p>
                    <button id="confirm-yes" class="btn btn-danger">Yes</button>
                    <button id="confirm-cancel" class="btn btn-secondary">Cancel</button>
                </div>
            `;
            document.body.appendChild(confirmBox);

            document.getElementById("confirm-yes").addEventListener("click", () => {
                fetch("/api/logout", { method: "POST" })
                    .then(() => window.location.href = "/")
                    .finally(() => confirmBox.remove());
            });

            document.getElementById("confirm-cancel").addEventListener("click", () => {
                confirmBox.remove();
            });
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
            showMessage(result.message || result.error, response.ok ? 'success' : 'error');
        });
    }

    const checkTokenBtn = document.getElementById('check-token-btn');
    if (checkTokenBtn) {
        checkTokenBtn.addEventListener('click', async () => {
            const statusEl = document.getElementById('token-status');
            statusEl.textContent = 'Checking...';
            try {
                const res = await fetch('/api/account_info');
                const data = await res.json();
                if (res.ok && data.has_token) {
                    statusEl.innerHTML = `<strong>${data.profile.username}</strong> (ID: ${data.profile.id})`;
                } else {
                    statusEl.textContent = data.message || 'No token saved.';
                }
            } catch (err) {
                statusEl.textContent = 'Error checking token.';
            }
        });
    }

    // --- Dashboard Analysis Logic ---
    const analyzeBtn = document.getElementById('analyze-btn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', async () => {
            const keywordInput = document.getElementById('keyword-input');
            const keyword = keywordInput.value.trim();
            if (!keyword) return alert('Please enter a keyword.');

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
                resultsContainer.innerHTML = `<div class="card"><p class="message error">An unexpected error occurred.</p></div>`;
            } finally {
                loader.classList.add('hidden');
                analyzeBtn.disabled = false;
            }
        });
    }
    
    const displayResults = (data) => {
        const resultsContainer = document.getElementById('results-container');
        
        let relatedTopicsHtml = '<li>No related topics found.</li>';
        if(data.related_topics && data.related_topics.length > 0) {
            relatedTopicsHtml = data.related_topics.slice(0, 5).map(topic => 
                `<li>${topic.title} (${topic.type})</li>`
            ).join('');
        }

        let relatedQueriesHtml = '<li>No related queries found.</li>';
        if(data.related_queries && data.related_queries.length > 0) {
            relatedQueriesHtml = data.related_queries.slice(0, 7).map(q => 
                `<li>${q.query} ${q.rising ? '<span style="color: #1a73e8; font-weight: bold;">(Rising!)</span>' : ''}</li>`
            ).join('');
        }

        let newsHtml = '<p>No news found.</p>';
        if (data.news_items && data.news_items.length > 0) {
            newsHtml = '<ul class="news-list">';
            data.news_items.slice(0, 5).forEach(item => {
                newsHtml += `
                    <li>
                        <a href="${item.link}" target="_blank">${item.title}</a>
                        <div class="news-meta">
                            ${item.source} • ${item.date}
                        </div>
                    </li>`;
            });
            newsHtml += '</ul>';
        }
        
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
                <h3>📰 Top News</h3>
                ${newsHtml}
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

    // --- THREADS PAGE LOGIC ---
    const threadsContainer = document.getElementById('threads-container');
    
    // Function to load account info immediately
    const loadAccountInfo = async () => {
        const accountInfoEl = document.getElementById('account-info');
        if (!accountInfoEl) return;
        
        accountInfoEl.textContent = 'Loading account info...';
        try {
            const res = await fetch('/api/account_info');
            const data = await res.json();
            if (res.ok && data.has_token) {
                const p = data.profile || {};
                const img = p.threads_profile_picture_url ? `<img src="${p.threads_profile_picture_url}" width="48" style="border-radius:50%; margin-right:8px; vertical-align: middle;">` : '';
                accountInfoEl.innerHTML = `${img} <strong>${p.username || '—'}</strong> (ID: ${p.id || '—'})<br>${p.threads_biography || ''}`;
            } else {
                accountInfoEl.innerHTML = `<span style="color:orange">${data.message || data.error || 'Token not configured.'}</span>`;
            }
        } catch (err) {
            accountInfoEl.textContent = 'Error contacting server.';
        }
    };

    // Auto-load account info if on Threads page
    if (document.getElementById('account-info')) {
        loadAccountInfo();
    }

    const refreshAccountBtn = document.getElementById('refresh-account-btn');
    if (refreshAccountBtn) {
        refreshAccountBtn.addEventListener('click', loadAccountInfo);
    }

    // Threads Logic: Timeline defaults
    const limitInput = document.getElementById('limit-input');
    const sinceInput = document.getElementById('since-input');
    const untilInput = document.getElementById('until-input');
    const useLimitDefault = document.getElementById('use-limit-default');
    const useSinceDefault = document.getElementById('use-since-default');
    const useUntilDefault = document.getElementById('use-until-default');

    if (useLimitDefault) useLimitDefault.addEventListener('click', () => { limitInput.value = 3; });
    if (useSinceDefault) useSinceDefault.addEventListener('click', () => { sinceInput.value = '2023-08-20'; });
    if (useUntilDefault) useUntilDefault.addEventListener('click', () => { untilInput.value = ''; });

    // Threads Logic: Fetch posts
    const fetchThreadsBtn = document.getElementById('fetch-threads-btn');
    if (fetchThreadsBtn) {
        fetchThreadsBtn.addEventListener('click', async () => {
            if (!threadsContainer) return;
            threadsContainer.innerHTML = 'Fetching posts...';
            fetchThreadsBtn.disabled = true;
            
            try {
                const payload = {
                    limit: parseInt(limitInput.value || 3),
                    since: sinceInput.value || null,
                    until: untilInput.value || 'now'
                };
                
                const res = await fetch('/api/fetch_threads', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const data = await res.json();
                
                if (!res.ok) {
                    threadsContainer.innerHTML = `<p class="message error">${data.error || 'Failed to fetch threads.'}</p>`;
                    return;
                }
                
                const posts = data.data || [];
                if (!posts.length) {
                    threadsContainer.innerHTML = '<p>No posts found for that timeframe.</p>';
                    return;
                }
                
                threadsContainer.innerHTML = posts.map(post => `
                    <div class="card" id="post-${post.id}">
                        <p><strong>Post ID:</strong> ${post.id}</p>
                        <p><strong>Text:</strong> ${post.text ? post.text : '<em>No text</em>'}</p>
                        <p><strong>Timestamp:</strong> ${post.timestamp || '—'}</p>
                        <p><a href="${post.permalink}" target="_blank">Open post</a></p>
                        <button class="btn analyze-post-btn" data-postid="${post.id}">Analyze Replies</button>
                        <div class="replies" id="replies-${post.id}" style="margin-top:0.75rem;"></div>
                    </div>
                `).join('');

                // Add event listeners to new buttons
                document.querySelectorAll('.analyze-post-btn').forEach(btn => {
                    btn.addEventListener('click', async (e) => {
                        const postId = btn.dataset.postid;
                        const repliesEl = document.getElementById(`replies-${postId}`);
                        repliesEl.innerHTML = 'Fetching replies and analyzing...';
                        btn.disabled = true;
                        
                        try {
                            const r = await fetch('/api/analyze_post', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ post_id: postId })
                            });
                            
                            const result = await r.json();
                            if (!r.ok) {
                                repliesEl.innerHTML = `<p class="message error">${result.error || 'Failed to analyze.'}</p>`;
                                return;
                            }

                            const analysis = result.analysis || {};
                            const replies = result.replies || [];
                            
                            // Build Reply List HTML
                            let perRepliesHtml = '';
                            if (analysis.per_reply && analysis.per_reply.length) {
                                perRepliesHtml = '<ul class="replies-list">' + analysis.per_reply.map(rep => `
                                    <li>
                                        <strong>${rep.username || 'User'}</strong>: ${rep.text} <br/>
                                        <span style="font-size:0.9em; color:#666;">Sentiment: ${rep.label} (${rep.score ? rep.score.toFixed(2) : '—'})</span>
                                    </li>
                                `).join('') + '</ul>';
                            } else if (replies.length) {
                                perRepliesHtml = '<p>No text replies available for sentiment.</p>';
                            } else {
                                perRepliesHtml = '<p>No replies found for this post.</p>';
                            }

                            // Build Recommendations HTML
                            const cumulative = analysis.cumulative_sentiment || 0.0;
                            const overall = analysis.overall_sentiment || '—';
                            const recommendations = (analysis.recommendations || []).map(r => `<li>${r}</li>`).join('');

                            let recommendationsHtml = `
                                <div class="card" style="background:#f0f9ff; border:1px solid #bae6fd;">
                                    <p><strong>Overall: ${overall}</strong> (Score: ${cumulative.toFixed(2)})</p>
                                    <ul>${recommendations}</ul>
                                </div>`;

                            // If negative/neutral, suggest the other tool
                            if (overall.toLowerCase().includes('negative') || overall.toLowerCase().includes('neutral')) {
                                recommendationsHtml += `<p style="margin-top:10px;">👉 Try the <a href="/dashboard">Keyword Recommendations</a> tool for content ideas.</p>`;
                            }

                            repliesEl.innerHTML = `${perRepliesHtml} ${recommendationsHtml}`;
                            
                        } catch (err) {
                            console.error(err);
                            repliesEl.innerHTML = '<p class="message error">Error analyzing replies.</p>';
                        } finally {
                            btn.disabled = false;
                        }
                    });
                });

            } catch (err) {
                console.error(err);
                if(threadsContainer) threadsContainer.innerHTML = '<p class="message error">An unexpected error occurred.</p>';
            } finally {
                fetchThreadsBtn.disabled = false;
            }
        });
    }
});