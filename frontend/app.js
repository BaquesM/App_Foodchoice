/**
 * FoodChoice Frontend Application Logic
 * Communicates with the FastAPI backend to fetch ingredients, accounts,
 * household profiles, and dynamic recipe recommendations with sharing and veto handling.
 * Integrates Supabase Auth for visitor vs authenticated user account management.
 */

// Supabase Auth Configuration
const SUPABASE_URL = "https://yazxsprryjbbmhdvoliv.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_W0dQg4JObKBzrlbhrS1W8A_S84hw3Ec";
let supabaseClient = null;

try {
    if (window.supabase) {
        supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    }
} catch (e) {
    console.warn("Supabase SDK initialization notice:", e);
}

function createEmptyRecipeFilters() {
    return {
        glutenFree: false,
        lactoseFree: false,
        vegetarian: false,
        vegan: false,
        inSeasonOnly: false,
        quickOnly: false,
        excludedAllergens: new Set(),
    };
}

// Global application state
const state = {
    allIngredients: [],
    allAllergens: [],
    allAccounts: [],
    searchRecipes: [],
    accountRecipes: [],
    recipeFilters: {
        search: createEmptyRecipeFilters(),
        myRecipes: createEmptyRecipeFilters(),
    },
    activeAccountId: null, // Default: null (Visiteur / Guest mode)
    currentUser: null,     // Currently authenticated user account object
    currentProfiles: [],
    selectedIngredientIds: new Set(),
    selectedProfileIds: new Set(),
    myRecipesSelectedProfileIds: new Set(),
    servings: 2,
    includePublic: true,
    filterQuery: "",
    currentView: "view-search",
    previousView: "view-search",
    loadedRecipesMap: new Map(),
    editingRecipeId: null,
    seasonCalFilterCategory: "all",
    seasonCalSearchQuery: "",
    seasonCalFilterSeason: "all",
    seasonCalFilterMonth: "all",
    seasonCalActiveCurrentMonthOnly: false,
    seasonCalIncludeYearRound: false
};

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

/**
 * Initialize application: check health, fetch initial accounts and ingredients, setup event listeners.
 */
async function initApp() {
    await checkApiHealth();
    await loadInitialData();
    setupEventListeners();
    setupAuthListeners();
    setupViewNavigation();
    await initAuthSession();
    renderSeasonCalendar();
    await handleSharedRecipeLink();
}

/**
 * If the URL contains ?share=<token>, fetch that shared recipe and open its detail view.
 */
async function handleSharedRecipeLink() {
    const params = new URLSearchParams(window.location.search);
    const shareToken = params.get("share");
    if (!shareToken) return;

    try {
        const res = await fetch(`/api/recipes/shared/${encodeURIComponent(shareToken)}`);
        if (!res.ok) {
            showToast("Lien de partage introuvable ou expiré.");
            return;
        }
        const rec = await res.json();
        state.loadedRecipesMap.set(rec.recipe_id, rec);
        openRecipeDetailPage(rec);
    } catch (error) {
        console.error("Failed to load shared recipe link:", error);
        showToast("Impossible de charger la recette partagée.");
    }
}

/**
 * Check backend API health and update badge status.
 */
async function checkApiHealth() {
    const statusCard = document.getElementById("status-card");

    try {
        const response = await fetch("/api/health");
        if (response.ok) {
            const data = await response.json();
            if (statusCard) {
                statusCard.className = "badge badge-success";
                statusCard.innerHTML = `<span class="badge-dot"></span><span>API v${data.version}</span>`;
            }
        } else {
            throw new Error(`HTTP ${response.status}`);
        }
    } catch (error) {
        if (statusCard) {
            statusCard.className = "badge badge-error";
            statusCard.innerHTML = `<span class="badge-dot"></span><span>API Hors ligne</span>`;
        }
        console.error("API health check failed:", error);
    }
}

/**
 * Fetch accounts and ingredients from backend.
 */
async function loadInitialData() {
    try {
        const [accRes, ingRes, allRes] = await Promise.all([
            fetch("/api/accounts"),
            fetch("/api/ingredients"),
            fetch("/api/allergens")
        ]);

        if (accRes.ok) {
            state.allAccounts = await accRes.json();
            renderAccountDropdown();
        }

        if (ingRes.ok) {
            state.allIngredients = await ingRes.json();
            renderIngredients();
            renderDatalist();
        }

        if (allRes.ok) {
            state.allAllergens = await allRes.json();
            renderAllergenFilterMenus();
        }

        // Load profiles for initial active account (if authenticated)
        if (state.activeAccountId) {
            await loadHouseholdProfiles(state.activeAccountId);
        } else {
            await loadHouseholdProfiles(null);
        }
    } catch (error) {
        console.error("Failed to load initial data:", error);
    }
}

/**
 * Render accounts dropdown options.
 */
function renderAccountDropdown() {
    const select = document.getElementById("account-select");
    if (!select) return;

    select.innerHTML = "";
    state.allAccounts.forEach((acc) => {
        const opt = document.createElement("option");
        opt.value = acc.id;
        opt.textContent = `${acc.display_name} (Connectée)`;
        if (acc.id === state.activeAccountId) opt.selected = true;
        select.appendChild(opt);
    });

    // Add Guest / Anonymous option
    const guestOpt = document.createElement("option");
    guestOpt.value = "";
    guestOpt.textContent = "👤 Visiteur (Sans compte)";
    select.appendChild(guestOpt);
}

/**
 * Load household profiles for an account.
 */
async function loadHouseholdProfiles(accountId) {
    state.selectedProfileIds.clear();
    state.myRecipesSelectedProfileIds.clear();
    const container = document.getElementById("profiles-selector");

    if (!accountId) {
        state.currentProfiles = [];
        if (container) {
            container.innerHTML = `<span class="text-muted text-sm">Mode invité : aucun profil de foyer (recherche neutre sans avis).</span>`;
        }
        renderMyRecipesProfiles();
        return;
    }

    try {
        const res = await fetch(`/api/accounts/${accountId}/profiles`);
        if (res.ok) {
            state.currentProfiles = await res.json();
            renderProfiles();
        }
    } catch (error) {
        console.error("Failed to load household profiles:", error);
    }
}

/**
 * Active profile currently being edited in preferences modal.
 */
let activePreferencesProfile = null;
let currentProfilePrefsMap = new Map();
let prefsFilterQuery = "";

/**
 * Render household profile toggle chips for the active account with preference settings.
 */
function renderProfiles() {
    const container = document.getElementById("profiles-selector");
    if (!container) return;

    container.innerHTML = "";

    state.currentProfiles.forEach((profile) => {
        const group = document.createElement("div");
        group.className = `chip-profile-group ${state.selectedProfileIds.has(profile.id) ? "active" : ""}`;

        const nameBtn = document.createElement("button");
        nameBtn.type = "button";
        nameBtn.className = "chip-profile-name";
        nameBtn.textContent = profile.name;
        nameBtn.title = `Cliquer pour inclure/exclure ${profile.name} du repas`;
        nameBtn.addEventListener("click", () => {
            if (state.selectedProfileIds.has(profile.id)) {
                state.selectedProfileIds.delete(profile.id);
            } else {
                state.selectedProfileIds.add(profile.id);
            }
            group.classList.toggle("active", state.selectedProfileIds.has(profile.id));
            triggerSearch();
        });

        const prefsBtn = document.createElement("button");
        prefsBtn.type = "button";
        prefsBtn.className = "btn-chip-prefs";
        prefsBtn.textContent = "⚙️";
        prefsBtn.title = `Gérer les goûts et vetos de ${profile.name}`;
        prefsBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            openPreferencesModal(profile);
        });

        group.appendChild(nameBtn);
        group.appendChild(prefsBtn);
        container.appendChild(group);
    });

    // Add "+ Convive" button to add a new person to the household
    const btnAddProfile = document.createElement("button");
    btnAddProfile.type = "button";
    btnAddProfile.className = "btn-add-profile";
    btnAddProfile.textContent = "+ Convive";
    btnAddProfile.title = "Ajouter un convive à votre foyer";
    btnAddProfile.addEventListener("click", () => {
        openAddProfileModal();
    });
    container.appendChild(btnAddProfile);

    renderMyRecipesProfiles();
}

/**
 * Render selectable guest pills in My Recipes header so vetoes only show for selected guests.
 */
function renderMyRecipesProfiles() {
    const container = document.getElementById("my-recipes-profiles-selector");
    if (!container) return;

    container.innerHTML = "";
    if (!state.activeAccountId || state.currentProfiles.length === 0) return;

    state.currentProfiles.forEach((profile) => {
        const group = document.createElement("div");
        group.className = `chip-profile-group ${state.myRecipesSelectedProfileIds.has(profile.id) ? "active" : ""}`;

        const nameBtn = document.createElement("button");
        nameBtn.type = "button";
        nameBtn.className = "chip-profile-name";
        nameBtn.textContent = profile.name;
        nameBtn.title = `Cliquer pour afficher les vétos de ${profile.name} sur vos recettes`;
        nameBtn.addEventListener("click", () => {
            if (state.myRecipesSelectedProfileIds.has(profile.id)) {
                state.myRecipesSelectedProfileIds.delete(profile.id);
            } else {
                state.myRecipesSelectedProfileIds.add(profile.id);
            }
            group.classList.toggle("active", state.myRecipesSelectedProfileIds.has(profile.id));
            loadAccountRecipes();
        });

        const prefsBtn = document.createElement("button");
        prefsBtn.type = "button";
        prefsBtn.className = "btn-chip-prefs";
        prefsBtn.textContent = "⚙️";
        prefsBtn.title = `Gérer les goûts et vetos de ${profile.name}`;
        prefsBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            openPreferencesModal(profile);
        });

        group.appendChild(nameBtn);
        group.appendChild(prefsBtn);
        container.appendChild(group);
    });
}

/**
 * Open modal to add a new household profile.
 */
function openAddProfileModal() {
    const modal = document.getElementById("modal-add-profile");
    const input = document.getElementById("new-profile-name");
    if (modal && input) {
        input.value = "";
        modal.style.display = "flex";
        input.focus();
    }
}

/**
 * Close modal to add a new household profile.
 */
function closeAddProfileModal() {
    const modal = document.getElementById("modal-add-profile");
    if (modal) modal.style.display = "none";
}

/**
 * Open modal to edit ingredient preferences for a specific household profile.
 */
async function openPreferencesModal(profile) {
    activePreferencesProfile = profile;
    currentProfilePrefsMap.clear();
    prefsFilterQuery = "";

    const modal = document.getElementById("modal-profile-prefs");
    const title = document.getElementById("prefs-modal-title");
    const filterInput = document.getElementById("prefs-ingredient-filter");
    const container = document.getElementById("prefs-ingredients-list");

    if (title) title.textContent = `🍽️ Goûts et préférences de ${profile.name}`;
    if (filterInput) filterInput.value = "";
    if (container) container.innerHTML = `<div class="loading-state">Chargement des préférences...</div>`;
    if (modal) modal.style.display = "flex";

    try {
        const res = await fetch(`/api/profiles/${profile.id}/preferences`);
        if (res.ok) {
            const prefs = await res.json();
            prefs.forEach((p) => {
                currentProfilePrefsMap.set(p.ingredient_id, p.rating);
            });
        }
    } catch (err) {
        console.error("Failed to load profile preferences:", err);
    }

    renderProfileDietAndAllergens();
    renderPreferencesList();
}

/**
 * Render vegetarian, vegan and allergen toggle pills for activePreferencesProfile.
 */
function renderProfileDietAndAllergens() {
    const dietContainer = document.getElementById("prefs-diet-pills");
    const allergenContainer = document.getElementById("prefs-allergen-pills");
    if (!dietContainer || !allergenContainer || !activePreferencesProfile) return;

    const profile = activePreferencesProfile;
    const currentAllergens = new Set(profile.allergens || []);

    async function saveProfileDiet(nextVeg, nextVegan, nextAllergensSet) {
        const payload = {
            is_vegetarian: nextVeg,
            is_vegan: nextVegan,
            allergens: Array.from(nextAllergensSet),
        };
        try {
            const res = await fetch(`/api/profiles/${profile.id}/diet`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (res.ok) {
                const updated = await res.json();
                profile.is_vegetarian = updated.is_vegetarian;
                profile.is_vegan = updated.is_vegan;
                profile.allergens = updated.allergens || [];
                const idx = state.currentProfiles.findIndex((p) => p.id === profile.id);
                if (idx !== -1) state.currentProfiles[idx] = { ...state.currentProfiles[idx], ...updated };
                renderProfileDietAndAllergens();
                if (state.currentView === "view-search" && state.selectedProfileIds.has(profile.id)) {
                    triggerSearch();
                } else if (state.currentView === "view-my-recipes" && state.myRecipesSelectedProfileIds.has(profile.id)) {
                    loadAccountRecipes();
                }
            }
        } catch (err) {
            console.error("Failed to update profile diet/allergens:", err);
            showToast("Erreur lors de la sauvegarde du régime.");
        }
    }

    dietContainer.innerHTML = "";
    [
        { key: "is_vegetarian", label: "🥗 Végétarien", active: Boolean(profile.is_vegetarian) },
        { key: "is_vegan", label: "🌱 Végan", active: Boolean(profile.is_vegan) },
    ].forEach((item) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `pref-toggle-pill pref-toggle-diet ${item.active ? "active" : ""}`;
        btn.textContent = item.label;
        btn.addEventListener("click", () => {
            const nextVeg = item.key === "is_vegetarian" ? !profile.is_vegetarian : Boolean(profile.is_vegetarian);
            const nextVegan = item.key === "is_vegan" ? !profile.is_vegan : Boolean(profile.is_vegan);
            saveProfileDiet(nextVeg, nextVegan, currentAllergens);
        });
        dietContainer.appendChild(btn);
    });

    allergenContainer.innerHTML = "";
    state.allAllergens.forEach((a) => {
        const isActive = currentAllergens.has(a.name);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `pref-toggle-pill pref-toggle-allergen ${isActive ? "active" : ""}`;
        const icon = ALLERGEN_ICONS[a.name] || "⚠️";
        btn.textContent = `${icon} ${a.label}`;
        btn.addEventListener("click", () => {
            const nextSet = new Set(currentAllergens);
            if (nextSet.has(a.name)) nextSet.delete(a.name);
            else nextSet.add(a.name);
            saveProfileDiet(Boolean(profile.is_vegetarian), Boolean(profile.is_vegan), nextSet);
        });
        allergenContainer.appendChild(btn);
    });
}

/**
 * Close preferences modal.
 */
function closePreferencesModal() {
    const modal = document.getElementById("modal-profile-prefs");
    if (modal) modal.style.display = "none";
    activePreferencesProfile = null;
}

/**
 * Render ingredients with rating controls in preferences modal.
 */
function renderPreferencesList() {
    const container = document.getElementById("prefs-ingredients-list");
    if (!container || !activePreferencesProfile) return;

    const filtered = state.allIngredients.filter((ing) => {
        if (!prefsFilterQuery) return true;
        return (
            ing.name.toLowerCase().includes(prefsFilterQuery) ||
            ing.category.toLowerCase().includes(prefsFilterQuery)
        );
    });

    if (filtered.length === 0) {
        container.innerHTML = `<div class="empty-state">Aucun ingrédient correspondant à "${prefsFilterQuery}"</div>`;
        return;
    }

    container.innerHTML = "";
    filtered.forEach((ing) => {
        const row = document.createElement("div");
        row.className = "pref-item-row";

        const info = document.createElement("div");
        info.className = "pref-ing-info";
        info.innerHTML = `
            <span class="pref-ing-name">${ing.name}</span>
            <span class="pref-ing-cat">${ing.category}</span>
        `;

        const currentRating = currentProfilePrefsMap.get(ing.id) ?? 0;

        const ratingGroup = document.createElement("div");
        ratingGroup.className = "rating-buttons-group";

        const ratingsConfig = [
            { rating: -2, label: "🚫 Veto", class: "active-veto", title: "Détesté / Veto absolu (-2)" },
            { rating: -1, label: "🙁 Pas fan", class: "active-dislike", title: "Pas aimé (-1)" },
            { rating: 0, label: "😐 Neutre", class: "active-neutral", title: "Neutre (0)" },
            { rating: 1, label: "🙂 Aimé", class: "active-like", title: "Aimé (+1)" },
            { rating: 2, label: "😍 Adoré", class: "active-love", title: "Adoré (+2)" },
        ];

        ratingsConfig.forEach((cfg) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = `btn-rate ${currentRating === cfg.rating ? cfg.class : ""}`;
            btn.textContent = cfg.label;
            btn.title = cfg.title;

            btn.addEventListener("click", async () => {
                await updateProfileIngredientRating(activePreferencesProfile.id, ing.id, cfg.rating);
                currentProfilePrefsMap.set(ing.id, cfg.rating);
                // Re-render button states in this row
                ratingGroup.querySelectorAll(".btn-rate").forEach((b, idx) => {
                    const c = ratingsConfig[idx];
                    b.className = `btn-rate ${cfg.rating === c.rating ? c.class : ""}`;
                });
            });

            ratingGroup.appendChild(btn);
        });

        row.appendChild(info);
        row.appendChild(ratingGroup);
        container.appendChild(row);
    });
}

/**
 * Send preference rating update to backend API.
 */
async function updateProfileIngredientRating(profileId, ingredientId, rating) {
    try {
        const res = await fetch("/api/preferences", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                profile_id: profileId,
                ingredient_id: ingredientId,
                rating: rating,
            }),
        });

        if (res.ok) {
            // If profile is currently dining, refresh recipe recommendations immediately
            if (state.selectedProfileIds.has(profileId)) {
                triggerSearch();
            }
        }
    } catch (err) {
        console.error("Failed to update preference:", err);
    }
}

/**
 * Setup view navigation tabs.
 */
function setupViewNavigation() {
    const tabButtons = document.querySelectorAll(".tab-btn");

    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetViewId = btn.getAttribute("data-view");
            if (targetViewId === "view-create-recipe") {
                resetRecipeFormToCreateMode();
            }
            switchView(targetViewId);
        });
    });

    // Direct buttons for creation view
    const btnGoCreate = document.getElementById("btn-go-to-create");
    if (btnGoCreate) {
        btnGoCreate.addEventListener("click", () => {
            resetRecipeFormToCreateMode();
            switchView("view-create-recipe");
        });
    }

    const btnCancelCreate = document.getElementById("btn-cancel-create");
    const btnCancelSecondary = document.getElementById("btn-cancel-create-secondary");
    if (btnCancelCreate) {
        btnCancelCreate.addEventListener("click", () => {
            resetRecipeFormToCreateMode();
            switchView("view-my-recipes");
        });
    }
    if (btnCancelSecondary) {
        btnCancelSecondary.addEventListener("click", () => {
            resetRecipeFormToCreateMode();
            switchView("view-my-recipes");
        });
    }
}

/**
 * Switch the displayed view between Search, My Recipes, and Create Recipe.
 */
function switchView(viewId) {
    if (viewId === "view-create-recipe" && !state.activeAccountId) {
        showToast("Veuillez sélectionner un compte connecté pour créer une recette.");
        return;
    }

    if (viewId !== "view-recipe-detail") {
        state.previousView = viewId;
    }

    state.currentView = viewId;

    // Toggle view sections
    document.querySelectorAll(".app-view").forEach((view) => {
        view.style.display = view.id === viewId ? "block" : "none";
    });

    // Toggle active tab buttons
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        const matches = btn.getAttribute("data-view") === viewId;
        btn.classList.toggle("active", matches);
    });

    // View specific initialization
    if (viewId === "view-my-recipes") {
        state.editingRecipeId = null;
        loadAccountRecipes();
    } else if (viewId === "view-create-recipe") {
        if (!state.editingRecipeId) {
            resetRecipeFormToCreateMode();
        }
    } else if (viewId === "view-search") {
        state.editingRecipeId = null;
        triggerSearch();
    } else if (viewId === "view-season-calendar") {
        state.editingRecipeId = null;
        renderSeasonCalendar();
    }
}

/**
 * Update UI elements depending on whether user is logged in or a guest.
 */
function updateAccountViewUI() {
    const tabMyRecipes = document.getElementById("tab-my-recipes");
    const tabCreateRecipe = document.getElementById("tab-create-recipe");
    const btnGoCreate = document.getElementById("btn-go-to-create");
    const myRecipesSubtitle = document.getElementById("my-recipes-subtitle");
    const myRecipesProfiles = document.getElementById("my-recipes-profiles-selector");
    const groupWhoIsDining = document.getElementById("group-who-is-dining");
    const controlsGrid = document.querySelector(".controls-grid");
    const publicToggleContainer = document.querySelector(".public-toggle-container");
    const toggleIncludePublic = document.getElementById("toggle-include-public");

    const authVisitor = document.getElementById("auth-state-visitor");
    const authLogged = document.getElementById("auth-state-logged");
    const loggedName = document.getElementById("logged-user-name");

    if (state.activeAccountId && state.currentUser) {
        // Logged-in user account
        if (authVisitor) authVisitor.style.display = "none";
        if (authLogged) authLogged.style.display = "flex";
        if (loggedName) loggedName.textContent = state.currentUser.display_name;

        if (tabMyRecipes) tabMyRecipes.innerHTML = "📖 Mes Recettes";
        if (tabCreateRecipe) tabCreateRecipe.style.display = "";
        if (btnGoCreate) btnGoCreate.style.display = "";
        if (groupWhoIsDining) groupWhoIsDining.style.display = "";
        if (publicToggleContainer) publicToggleContainer.style.display = "";
        if (controlsGrid) controlsGrid.classList.remove("visitor-mode");
        if (myRecipesSubtitle) myRecipesSubtitle.style.display = "none";
        if (myRecipesProfiles) myRecipesProfiles.style.display = "flex";
    } else {
        // Visitor / Guest mode
        if (authVisitor) authVisitor.style.display = "flex";
        if (authLogged) authLogged.style.display = "none";

        if (tabMyRecipes) tabMyRecipes.innerHTML = "📖 Recettes";
        if (tabCreateRecipe) tabCreateRecipe.style.display = "none";
        if (btnGoCreate) btnGoCreate.style.display = "none";
        if (groupWhoIsDining) groupWhoIsDining.style.display = "none";
        if (publicToggleContainer) publicToggleContainer.style.display = "none";
        state.includePublic = true;
        if (toggleIncludePublic) toggleIncludePublic.checked = true;
        if (controlsGrid) controlsGrid.classList.add("visitor-mode");
        if (myRecipesSubtitle) {
            myRecipesSubtitle.style.display = "";
            myRecipesSubtitle.textContent = "Toutes les recettes publiques partagées par la communauté.";
        }
        if (myRecipesProfiles) myRecipesProfiles.style.display = "none";
        if (state.currentView === "view-create-recipe") {
            switchView("view-search");
        }
    }
}

/**
 * Initialize and restore active Supabase Auth session on app launch.
 */
async function initAuthSession() {
    if (!supabaseClient) {
        updateAccountViewUI();
        return;
    }

    try {
        const { data } = await supabaseClient.auth.getSession();
        const session = data ? data.session : null;
        if (session && session.user) {
            await syncAndActivateUser(session.user);
        } else {
            state.activeAccountId = null;
            state.currentUser = null;
            updateAccountViewUI();
            await loadHouseholdProfiles(null);
        }

        // Listen for auth state changes (e.g. login/logout in other tabs or token refresh)
        supabaseClient.auth.onAuthStateChange(async (event, currentSession) => {
            if (event === "SIGNED_IN" && currentSession && currentSession.user) {
                if (state.currentUser?.supabase_uid !== currentSession.user.id) {
                    await syncAndActivateUser(currentSession.user);
                }
            } else if (event === "SIGNED_OUT") {
                state.activeAccountId = null;
                state.currentUser = null;
                updateAccountViewUI();
                await loadHouseholdProfiles(null);
                if (state.currentView === "view-my-recipes") {
                    loadAccountRecipes();
                } else if (state.currentView === "view-create-recipe") {
                    switchView("view-search");
                } else {
                    triggerSearch();
                }
            }
        });
    } catch (err) {
        console.error("Failed to restore Supabase auth session:", err);
        state.activeAccountId = null;
        state.currentUser = null;
        updateAccountViewUI();
    }
}

/**
 * Synchronize authenticated Supabase user profile with the backend database.
 */
async function syncAndActivateUser(supabaseUser) {
    if (!supabaseUser) return;
    try {
        const payload = {
            supabase_uid: supabaseUser.id,
            email: supabaseUser.email,
            display_name: supabaseUser.user_metadata?.display_name || supabaseUser.email.split("@")[0]
        };

        const res = await fetch("/api/auth/sync", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const acc = await res.json();
            state.activeAccountId = acc.id;
            state.currentUser = acc;

            // Refresh allAccounts list
            const accRes = await fetch("/api/accounts");
            if (accRes.ok) {
                state.allAccounts = await accRes.json();
            }

            updateAccountViewUI();
            await loadHouseholdProfiles(acc.id);
            await loadAccountNotifications();

            if (state.currentView === "view-my-recipes") {
                loadAccountRecipes();
            } else {
                triggerSearch();
            }
        } else {
            console.error("Failed to sync Supabase user with backend:", await res.text());
        }
    } catch (err) {
        console.error("Error syncing Supabase user with backend:", err);
    }
}

/**
 * Setup Supabase authentication modal and user interaction listeners.
 */
function setupAuthListeners() {
    const modal = document.getElementById("auth-modal");
    const btnOpenLogin = document.getElementById("btn-open-login");
    const btnOpenRegister = document.getElementById("btn-open-register");
    const btnCloseModal = document.getElementById("btn-close-auth-modal");
    const tabSwitchLogin = document.getElementById("tab-switch-login");
    const tabSwitchRegister = document.getElementById("tab-switch-register");
    const formLogin = document.getElementById("form-login");
    const formRegister = document.getElementById("form-register");
    const loginError = document.getElementById("login-error-msg");
    const registerError = document.getElementById("register-error-msg");
    const btnLogout = document.getElementById("btn-logout");

    function openModal(mode = "login") {
        if (!modal) return;
        modal.style.display = "flex";
        if (loginError) loginError.style.display = "none";
        if (registerError) registerError.style.display = "none";

        if (mode === "login") {
            tabSwitchLogin?.classList.add("active");
            tabSwitchRegister?.classList.remove("active");
            if (formLogin) formLogin.style.display = "flex";
            if (formRegister) formRegister.style.display = "none";
        } else {
            tabSwitchRegister?.classList.add("active");
            tabSwitchLogin?.classList.remove("active");
            if (formRegister) formRegister.style.display = "flex";
            if (formLogin) formLogin.style.display = "none";
        }
    }

    function closeModal() {
        if (modal) modal.style.display = "none";
    }

    btnOpenLogin?.addEventListener("click", () => openModal("login"));
    btnOpenRegister?.addEventListener("click", () => openModal("register"));
    btnCloseModal?.addEventListener("click", closeModal);

    modal?.addEventListener("click", (e) => {
        if (e.target === modal) closeModal();
    });

    tabSwitchLogin?.addEventListener("click", () => openModal("login"));
    tabSwitchRegister?.addEventListener("click", () => openModal("register"));

    // Login form submission
    formLogin?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("login-email")?.value.trim();
        const password = document.getElementById("login-password")?.value;
        const btnSubmit = document.getElementById("btn-submit-login");

        if (!email || !password) return;
        if (!supabaseClient) {
            if (loginError) {
                loginError.textContent = "Le service d'authentification Supabase n'est pas disponible.";
                loginError.style.display = "block";
            }
            return;
        }

        try {
            if (btnSubmit) {
                btnSubmit.disabled = true;
                btnSubmit.textContent = "Connexion en cours...";
            }
            if (loginError) loginError.style.display = "none";

            const { data, error } = await supabaseClient.auth.signInWithPassword({
                email,
                password
            });

            if (error) {
                let msg = error.message;
                if (msg.includes("Invalid login credentials")) {
                    msg = "Adresse email ou mot de passe incorrect.";
                } else if (msg.includes("Email not confirmed")) {
                    msg = "Votre adresse email n'a pas encore été confirmée. Veuillez vérifier votre boîte mail ou désactiver la confirmation dans Supabase.";
                }
                if (loginError) {
                    loginError.textContent = msg;
                    loginError.style.display = "block";
                }
                return;
            }

            if (data?.user) {
                await syncAndActivateUser(data.user);
                closeModal();
                showToast(`Bienvenue ${state.currentUser?.display_name || ''} !`);
            }
        } catch (err) {
            console.error("Login submission error:", err);
            if (loginError) {
                loginError.textContent = "Une erreur est survenue lors de la connexion.";
                loginError.style.display = "block";
            }
        } finally {
            if (btnSubmit) {
                btnSubmit.disabled = false;
                btnSubmit.textContent = "Se connecter";
            }
        }
    });

    // Registration form submission
    formRegister?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("register-name")?.value.trim();
        const email = document.getElementById("register-email")?.value.trim();
        const password = document.getElementById("register-password")?.value;
        const btnSubmit = document.getElementById("btn-submit-register");

        if (!name || !email || !password) return;
        if (!supabaseClient) {
            if (registerError) {
                registerError.textContent = "Le service d'authentification Supabase n'est pas disponible.";
                registerError.style.display = "block";
            }
            return;
        }

        try {
            if (btnSubmit) {
                btnSubmit.disabled = true;
                btnSubmit.textContent = "Création du compte...";
            }
            if (registerError) registerError.style.display = "none";

            const { data, error } = await supabaseClient.auth.signUp({
                email,
                password,
                options: {
                    data: { display_name: name }
                }
            });

            if (error) {
                let msg = error.message;
                if (msg.includes("already registered")) {
                    msg = "Un compte existe déjà avec cette adresse email.";
                } else if (msg.includes("Password should be")) {
                    msg = "Le mot de passe doit comporter au moins 6 caractères.";
                }
                if (registerError) {
                    registerError.textContent = msg;
                    registerError.style.display = "block";
                }
                return;
            }

            if (data?.session && data?.user) {
                // Auto logged-in
                await syncAndActivateUser(data.user);
                closeModal();
                showToast(`Compte créé avec succès ! Bienvenue ${name}.`);
            } else if (data?.user) {
                if (registerError) {
                    registerError.className = "auth-error-alert";
                    registerError.style.backgroundColor = "#ecfdf5";
                    registerError.style.color = "#065f46";
                    registerError.style.borderColor = "#a7f3d0";
                    registerError.textContent = "Compte créé avec succès ! Vous pouvez maintenant vous connecter.";
                    registerError.style.display = "block";
                }
                setTimeout(() => openModal("login"), 1500);
            }
        } catch (err) {
            console.error("Registration submission error:", err);
            if (registerError) {
                registerError.textContent = "Une erreur est survenue lors de l'inscription.";
                registerError.style.display = "block";
            }
        } finally {
            if (btnSubmit) {
                btnSubmit.disabled = false;
                btnSubmit.textContent = "Créer mon compte";
            }
        }
    });

    // Logout button
    btnLogout?.addEventListener("click", async () => {
        try {
            if (supabaseClient) {
                await supabaseClient.auth.signOut();
            }
            state.activeAccountId = null;
            state.currentUser = null;
            updateAccountViewUI();
            await loadHouseholdProfiles(null);
            showToast("Vous avez été déconnecté.");

            if (state.currentView === "view-my-recipes") {
                loadAccountRecipes();
            } else if (state.currentView === "view-create-recipe") {
                switchView("view-search");
            } else {
                triggerSearch();
            }
        } catch (err) {
            console.error("Logout failed:", err);
        }
    });
}

/**
 * Load and display pending notifications for recipes modified by their authors.
 */
async function loadAccountNotifications() {
    const container = document.getElementById("shared-recipe-notifications");
    if (!container) return;

    if (!state.activeAccountId) {
        container.style.display = "none";
        container.innerHTML = "";
        return;
    }

    try {
        const res = await fetch(`/api/accounts/${state.activeAccountId}/notifications`);
        if (res.ok) {
            const notifs = await res.json();
            if (notifs.length === 0) {
                container.style.display = "none";
                container.innerHTML = "";
                return;
            }

            container.style.display = "flex";
            container.innerHTML = notifs.map(n => `
                <div class="notification-banner-card" data-notif-id="${n.id}">
                    <div class="notif-text">
                        <span style="font-size: 1.5rem;">🔔</span>
                        <div>
                            <strong>Modification d'une recette partagée par ${n.author_name} :</strong>
                            <p style="margin: 0.25rem 0 0 0; font-size: 0.9rem;">${n.message}</p>
                        </div>
                    </div>
                    <div class="notif-actions">
                        <button type="button" class="btn-primary btn-sm btn-accept-notif" data-id="${n.id}">
                            ✓ Accepter la modification
                        </button>
                        <button type="button" class="btn-secondary btn-sm btn-reject-notif" data-id="${n.id}">
                            ✕ Conserver ma version précédente
                        </button>
                    </div>
                </div>
            `).join("");

            container.querySelectorAll(".btn-accept-notif").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const id = btn.getAttribute("data-id");
                    await respondToRecipeNotification(id, "accept");
                });
            });

            container.querySelectorAll(".btn-reject-notif").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const id = btn.getAttribute("data-id");
                    await respondToRecipeNotification(id, "reject");
                });
            });
        }
    } catch (err) {
        console.error("Failed to load notifications:", err);
    }
}

/**
 * Send response (accept / reject) to a shared recipe update notification.
 */
async function respondToRecipeNotification(notificationId, action) {
    try {
        const res = await fetch(`/api/notifications/${notificationId}/respond`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: action })
        });
        if (res.ok) {
            const data = await res.json();
            showToast(data.message || "Réponse enregistrée.");
            await loadAccountNotifications();
            await loadAccountRecipes();
        } else {
            showToast("Erreur lors de la réponse à la notification.");
        }
    } catch (err) {
        console.error("Error responding to notification:", err);
    }
}

/**
 * Load and render all recipes belonging to the active account or all public recipes for guests.
 */
async function loadAccountRecipes() {
    await loadAccountNotifications();
    const container = document.getElementById("my-recipes-list");
    const subtitle = document.getElementById("my-recipes-subtitle");
    if (!container) return;

    if (!state.activeAccountId) {
        // Visitor mode: fetch all public recipes
        if (subtitle) {
            subtitle.textContent = "Toutes les recettes publiques partagées par la communauté.";
        }
        container.innerHTML = `<div class="loading-state">Chargement des recettes publiques...</div>`;

        try {
            const res = await fetch("/api/recipes/public");
            if (res.ok) {
                state.accountRecipes = await res.json();
                applyRecipeFilters("myRecipes");
            } else {
                throw new Error(`HTTP ${res.status}`);
            }
        } catch (err) {
            console.error("Failed to load public recipes for visitor:", err);
            container.innerHTML = `<div class="empty-state text-danger">Erreur lors du chargement des recettes publiques.</div>`;
        }
        return;
    }

    container.innerHTML = `<div class="loading-state">Chargement de vos recettes...</div>`;

    try {
        const params = new URLSearchParams();
        state.myRecipesSelectedProfileIds.forEach((pid) => params.append("profile_ids", pid));
        const qs = params.toString() ? `?${params.toString()}` : "";
        const res = await fetch(`/api/accounts/${state.activeAccountId}/recipes${qs}`);
        if (res.ok) {
            state.accountRecipes = await res.json();
            applyRecipeFilters("myRecipes");
        } else {
            throw new Error(`HTTP ${res.status}`);
        }
    } catch (err) {
        console.error("Failed to load account recipes:", err);
        container.innerHTML = `<div class="empty-state text-danger">Erreur lors du chargement des recettes de ce compte.</div>`;
    }
}

/**
 * Filter a recipe list according to active diet, allergen, seasonality, and quick-time filters.
 */
function filterRecipeList(recipes, f) {
    return recipes.filter((r) => {
        const allergens = r.allergens || [];
        if (f.glutenFree && allergens.includes("gluten")) return false;
        if (f.lactoseFree && allergens.includes("lait")) return false;
        if (f.vegetarian && r.is_vegetarian === false) return false;
        if (f.vegan && r.is_vegan === false) return false;
        if (f.inSeasonOnly && r.seasonality_score < 100) return false;
        if (f.quickOnly && ((r.prep_time_minutes || 0) + (r.cook_time_minutes || 0)) > 20) return false;
        for (const slug of f.excludedAllergens) {
            if (allergens.includes(slug)) return false;
        }
        return true;
    });
}

/**
 * Populate the multi-select allergen dropdown checklists across all recipe filter bars.
 */
function renderAllergenFilterMenus() {
    document.querySelectorAll("[data-filter-scope]").forEach((bar) => {
        const scope = bar.dataset.filterScope;
        const list = bar.querySelector(".allergen-checkbox-list");
        const filters = state.recipeFilters[scope];
        if (!list || !filters) return;

        list.innerHTML = "";
        state.allAllergens.forEach((allergen) => {
            const label = document.createElement("label");
            label.className = "allergen-checkbox-item";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.value = allergen.name;
            checkbox.checked = filters.excludedAllergens.has(allergen.name);
            checkbox.addEventListener("change", () => {
                if (checkbox.checked) {
                    filters.excludedAllergens.add(allergen.name);
                } else {
                    filters.excludedAllergens.delete(allergen.name);
                }
                applyRecipeFilters(scope);
            });

            const text = document.createElement("span");
            text.textContent = allergen.label;

            label.appendChild(checkbox);
            label.appendChild(text);
            list.appendChild(label);
        });
    });
}

/**
 * Apply active filters for either "search" or "myRecipes" scope and re-render cards.
 */
function applyRecipeFilters(scope) {
    const bar = document.querySelector(`[data-filter-scope="${scope}"]`);
    const f = state.recipeFilters[scope];
    if (!f) return;

    const excludedCount = f.excludedAllergens.size;
    if (bar) {
        const countSpan = bar.querySelector(".allergen-filter-count");
        const allergenBtn = bar.querySelector(".allergen-dropdown-btn");
        if (countSpan) countSpan.textContent = excludedCount > 0 ? `(${excludedCount})` : "";
        if (allergenBtn) allergenBtn.classList.toggle("active", excludedCount > 0);

        const hasActiveFilter =
            f.glutenFree || f.lactoseFree || f.vegetarian || f.vegan ||
            f.inSeasonOnly || f.quickOnly || excludedCount > 0;
        const resetBtn = bar.querySelector(".recipe-filter-reset");
        if (resetBtn) resetBtn.style.display = hasActiveFilter ? "inline-flex" : "none";
    }

    if (scope === "myRecipes") {
        const container = document.getElementById("my-recipes-list");
        if (!container) return;

        if (state.accountRecipes.length === 0) {
            container.innerHTML = state.activeAccountId
                ? `<div class="empty-state">Vous n'avez pas encore de recette enregistrée ou partagée. Cliquez sur « ➕ Créer une nouvelle recette » pour commencer !</div>`
                : `<div class="empty-state">Aucune recette publique disponible pour le moment.</div>`;
            return;
        }

        const filtered = filterRecipeList(state.accountRecipes, f);
        if (filtered.length === 0) {
            container.innerHTML = `<div class="empty-state">Aucune recette ne correspond aux filtres sélectionnés.</div>`;
        } else {
            renderRecipeCards(filtered, "my-recipes-list", false);
        }
        return;
    }

    if (scope === "search") {
        const container = document.getElementById("recipes-list");
        const countSpan = document.getElementById("results-count");
        if (!container) return;

        if (state.selectedIngredientIds.size === 0) {
            if (countSpan) countSpan.textContent = "0";
            container.innerHTML = `<div class="empty-state">Sélectionnez au moins un ingrédient ci-dessus pour découvrir vos recettes.</div>`;
            return;
        }

        const filtered = filterRecipeList(state.searchRecipes, f);
        if (countSpan) countSpan.textContent = filtered.length;
        if (state.searchRecipes.length === 0) {
            container.innerHTML = `<div class="empty-state">Aucune recette ne contient ces ingrédients. Essayez d'en sélectionner d'autres !</div>`;
        } else if (filtered.length === 0) {
            container.innerHTML = `<div class="empty-state">Aucune recette compatible avec vos ingrédients ne correspond aux filtres sélectionnés.</div>`;
        } else {
            renderRecipeCards(filtered, "recipes-list", true);
        }
    }
}

/**
 * Bind click listeners for all recipe filter bars (Search and My Recipes / Visitor Recipes).
 */
function setupRecipeFilterBarListeners() {
    document.querySelectorAll("[data-filter-scope]").forEach((bar) => {
        const scope = bar.dataset.filterScope;
        const filters = state.recipeFilters[scope];
        if (!filters) return;

        bar.querySelectorAll("[data-recipe-filter]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const key = btn.dataset.recipeFilter;
                if (!key || !(key in filters)) return;
                filters[key] = !filters[key];
                btn.classList.toggle("active", filters[key]);
                applyRecipeFilters(scope);
            });
        });

        const dropdown = bar.querySelector(".allergen-dropdown");
        const dropdownBtn = bar.querySelector(".allergen-dropdown-btn");
        const dropdownMenu = bar.querySelector(".allergen-dropdown-menu");

        if (dropdownBtn && dropdownMenu) {
            dropdownBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                const isOpen = dropdownMenu.style.display !== "none";
                dropdownMenu.style.display = isOpen ? "none" : "block";
                dropdownBtn.setAttribute("aria-expanded", String(!isOpen));
            });

            document.addEventListener("click", (e) => {
                if (dropdown && !dropdown.contains(e.target) && dropdownMenu.style.display !== "none") {
                    dropdownMenu.style.display = "none";
                    dropdownBtn.setAttribute("aria-expanded", "false");
                }
            });
        }

        const resetBtn = bar.querySelector(".recipe-filter-reset");
        if (resetBtn) {
            resetBtn.addEventListener("click", () => {
                filters.glutenFree = false;
                filters.lactoseFree = false;
                filters.vegetarian = false;
                filters.vegan = false;
                filters.inSeasonOnly = false;
                filters.quickOnly = false;
                filters.excludedAllergens.clear();

                bar.querySelectorAll("[data-recipe-filter]").forEach((btn) => {
                    btn.classList.remove("active");
                });
                bar.querySelectorAll(".allergen-checkbox-list input[type='checkbox']").forEach((cb) => {
                    cb.checked = false;
                });

                applyRecipeFilters(scope);
            });
        }
    });
}

/**
 * Setup DOM event listeners.
 */
function setupEventListeners() {
    setupRecipeFilterBarListeners();

    // Account switch
    const accountSelect = document.getElementById("account-select");
    if (accountSelect) {
        accountSelect.addEventListener("change", async (e) => {
            const val = e.target.value;
            state.activeAccountId = val ? parseInt(val, 10) : null;
            updateAccountViewUI();
            await loadHouseholdProfiles(state.activeAccountId);
            await loadAccountNotifications();

            if (state.currentView === "view-my-recipes") {
                loadAccountRecipes();
            } else if (state.currentView === "view-create-recipe" && !state.activeAccountId) {
                switchView("view-search");
            } else {
                triggerSearch();
            }
        });
    }

    // Include public recipes toggle checkbox
    const togglePublic = document.getElementById("toggle-include-public");
    if (togglePublic) {
        togglePublic.addEventListener("change", (e) => {
            state.includePublic = e.target.checked;
            triggerSearch();
        });
    }

    // Add ingredient row button in recipe creator
    const btnAddRow = document.getElementById("btn-add-ingredient-row");
    if (btnAddRow) {
        btnAddRow.addEventListener("click", () => {
            addIngredientRow();
        });
    }

    // Add step row button in recipe creator
    const btnAddStep = document.getElementById("btn-add-step-row");
    if (btnAddStep) {
        btnAddStep.addEventListener("click", () => {
            addStepRow();
        });
    }

    // Recipe creation form submission
    const createForm = document.getElementById("create-recipe-form");
    if (createForm) {
        createForm.addEventListener("submit", handleCreateRecipeSubmit);
    }

    // Alternative recipe checkbox toggle
    const isAltCheckbox = document.getElementById("new-recipe-is-alternative");
    const altSelectBox = document.getElementById("alternative-recipe-select-box");
    if (isAltCheckbox && altSelectBox) {
        isAltCheckbox.addEventListener("change", async (e) => {
            if (e.target.checked) {
                altSelectBox.style.display = "block";
                await populateParentRecipeDropdown();
            } else {
                altSelectBox.style.display = "none";
            }
        });
    }

    // Quick filter input for pantry ingredients
    const filterInput = document.getElementById("ingredient-filter");
    if (filterInput) {
        filterInput.addEventListener("input", (e) => {
            state.filterQuery = e.target.value.toLowerCase().trim();
            renderIngredients();
        });
    }

    // Servings controls
    const servingsInput = document.getElementById("servings-input");
    const btnMinus = document.getElementById("btn-servings-minus");
    const btnPlus = document.getElementById("btn-servings-plus");

    if (servingsInput && btnMinus && btnPlus) {
        btnMinus.addEventListener("click", () => {
            let current = parseInt(servingsInput.value, 10) || 2;
            if (current > 1) {
                current--;
                servingsInput.value = current;
                state.servings = current;
                triggerSearch();
            }
        });

        btnPlus.addEventListener("click", () => {
            let current = parseInt(servingsInput.value, 10) || 2;
            if (current < 20) {
                current++;
                servingsInput.value = current;
                state.servings = current;
                triggerSearch();
            }
        });

        servingsInput.addEventListener("change", (e) => {
            let val = parseInt(e.target.value, 10);
            if (isNaN(val) || val < 1) val = 1;
            if (val > 20) val = 20;
            e.target.value = val;
            state.servings = val;
            triggerSearch();
        });
    }

    // Clear all selected pantry ingredients
    const btnClear = document.getElementById("btn-clear-selection");
    if (btnClear) {
        btnClear.addEventListener("click", () => {
            state.selectedIngredientIds.clear();
            renderIngredients();
            triggerSearch();
        });
    }

    // Back from recipe detail view button
    const btnBackDetail = document.getElementById("btn-back-from-detail");
    if (btnBackDetail) {
        btnBackDetail.addEventListener("click", () => {
            switchView(state.previousView || "view-search");
        });
    }

    // Season Calendar controls
    const calSearch = document.getElementById("calendar-search");
    if (calSearch) {
        calSearch.addEventListener("input", (e) => {
            state.seasonCalSearchQuery = e.target.value.toLowerCase().trim();
            renderSeasonCalendar();
        });
    }

    const calCatFilter = document.getElementById("calendar-category-filter");
    if (calCatFilter) {
        calCatFilter.addEventListener("change", (e) => {
            state.seasonCalFilterCategory = e.target.value;
            renderSeasonCalendar();
        });
    }

    const calMonthSelect = document.getElementById("calendar-month-select");
    const btnCurrentMonth = document.getElementById("btn-cal-current-month");
    const curMonthIndex = new Date().getMonth(); // 0 to 11
    const curMonthNum = curMonthIndex + 1;
    const curMonthNames = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];

    if (btnCurrentMonth) {
        btnCurrentMonth.textContent = `🌱 En ce moment (${curMonthNames[curMonthIndex]})`;
        btnCurrentMonth.addEventListener("click", () => {
            state.seasonCalActiveCurrentMonthOnly = !state.seasonCalActiveCurrentMonthOnly;
            btnCurrentMonth.classList.toggle("active", state.seasonCalActiveCurrentMonthOnly);

            if (state.seasonCalActiveCurrentMonthOnly) {
                state.seasonCalFilterMonth = String(curMonthNum);
                if (calMonthSelect) calMonthSelect.value = String(curMonthNum);
            } else {
                state.seasonCalFilterMonth = "all";
                if (calMonthSelect) calMonthSelect.value = "all";
            }
            renderSeasonCalendar();
        });
    }

    if (calMonthSelect) {
        calMonthSelect.addEventListener("change", (e) => {
            const val = e.target.value;
            state.seasonCalFilterMonth = val;
            const isCur = val === String(curMonthNum);
            state.seasonCalActiveCurrentMonthOnly = isCur;
            if (btnCurrentMonth) {
                btnCurrentMonth.classList.toggle("active", isCur);
            }
            renderSeasonCalendar();
        });
    }

    const calToggleYearRound = document.getElementById("calendar-toggle-year-round");
    if (calToggleYearRound) {
        calToggleYearRound.addEventListener("change", (e) => {
            state.seasonCalIncludeYearRound = e.target.checked;
            renderSeasonCalendar();
        });
    }

    // Modal: Add profile form
    const formAddProfile = document.getElementById("form-add-profile");
    if (formAddProfile) {
        formAddProfile.addEventListener("submit", async (e) => {
            e.preventDefault();
            const nameInput = document.getElementById("new-profile-name");
            const newName = nameInput ? nameInput.value.trim() : "";
            if (!newName || !state.activeAccountId) return;

            try {
                const res = await fetch(`/api/accounts/${state.activeAccountId}/profiles`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: newName }),
                });

                if (res.ok) {
                    const createdProfile = await res.json();
                    state.currentProfiles.push(createdProfile);
                    state.selectedProfileIds.add(createdProfile.id);
                    renderProfiles();
                    closeAddProfileModal();
                    showToast(`Convive "${newName}" ajouté au foyer !`);
                    triggerSearch();
                } else {
                    const err = await res.json();
                    showToast(err.detail || "Erreur lors de l'ajout du profil.");
                }
            } catch (err) {
                console.error("Failed to add profile:", err);
                showToast("Erreur réseau lors de l'ajout du profil.");
            }
        });
    }

    const btnCloseAddProfile = document.getElementById("btn-close-add-profile");
    const btnCancelAddProfile = document.getElementById("btn-cancel-add-profile");
    if (btnCloseAddProfile) btnCloseAddProfile.addEventListener("click", closeAddProfileModal);
    if (btnCancelAddProfile) btnCancelAddProfile.addEventListener("click", closeAddProfileModal);

    // Modal: Preferences
    const btnClosePrefs = document.getElementById("btn-close-prefs-modal");
    const btnDonePrefs = document.getElementById("btn-done-prefs");
    if (btnClosePrefs) btnClosePrefs.addEventListener("click", closePreferencesModal);
    if (btnDonePrefs) btnDonePrefs.addEventListener("click", closePreferencesModal);

    // Delete convive profile button in preferences modal
    const btnDeleteProfile = document.getElementById("btn-delete-profile");
    if (btnDeleteProfile) {
        btnDeleteProfile.addEventListener("click", async () => {
            if (!activePreferencesProfile) return;
            const prof = activePreferencesProfile;
            const confirmDelete = confirm(`Voulez-vous vraiment supprimer le convive "${prof.name}" et toutes ses préférences ?`);
            if (!confirmDelete) return;

            try {
                const res = await fetch(`/api/profiles/${prof.id}`, {
                    method: "DELETE"
                });
                if (res.ok) {
                    state.currentProfiles = state.currentProfiles.filter((p) => p.id !== prof.id);
                    state.selectedProfileIds.delete(prof.id);
                    closePreferencesModal();
                    renderProfiles();
                    showToast(`Convive "${prof.name}" supprimé avec succès.`);
                    triggerSearch();
                } else {
                    const err = await res.json();
                    showToast(err.detail || "Impossible de supprimer ce convive.");
                }
            } catch (err) {
                console.error("Failed to delete profile:", err);
                showToast("Erreur réseau lors de la suppression du convive.");
            }
        });
    }

    const prefsFilterInput = document.getElementById("prefs-ingredient-filter");
    if (prefsFilterInput) {
        prefsFilterInput.addEventListener("input", (e) => {
            prefsFilterQuery = e.target.value.toLowerCase().trim();
            renderPreferencesList();
        });
    }

    // Close modals on clicking backdrop
    window.addEventListener("click", (e) => {
        const modalAdd = document.getElementById("modal-add-profile");
        const modalPrefs = document.getElementById("modal-profile-prefs");
        if (e.target === modalAdd) closeAddProfileModal();
        if (e.target === modalPrefs) closePreferencesModal();
    });
}

/**
 * Add a dynamic ingredient input row in the recipe creation form.
 */
function addIngredientRow(data = null) {
    const container = document.getElementById("new-recipe-ingredients-list");
    if (!container) return;

    const item = document.createElement("div");
    item.className = "ingredient-form-item";

    // Unique ID for radio button grouping in this row
    if (!window._ingRowIdCounter) window._ingRowIdCounter = 0;
    const rowSeasonId = ++window._ingRowIdCounter;

    // Seasonality configuration panel for brand new ingredients
    const seasonBox = document.createElement("div");
    seasonBox.className = "seasonality-form-box";
    seasonBox.style.display = "none";

    seasonBox.innerHTML = `
        <div class="seasonality-header">
            <span class="seasonality-icon">🌱</span>
            <span class="seasonality-title">
                Saisonnalité pour <strong class="season-target-name"></strong> <span class="badge-new-ing">Nouvel ingrédient</span>
            </span>
        </div>
        <div class="seasonality-modes">
            <label class="season-mode-option">
                <input type="radio" name="season-mode-${rowSeasonId}" value="all_year" checked>
                <span>🌐 Toujours disponible (toute l'année)</span>
            </label>
            <label class="season-mode-option">
                <input type="radio" name="season-mode-${rowSeasonId}" value="custom_months">
                <span>📅 Mois spécifiques</span>
            </label>
            <label class="season-mode-option">
                <input type="radio" name="season-mode-${rowSeasonId}" value="unknown">
                <span>❓ Je ne sais pas (signaler à l'admin)</span>
            </label>
        </div>
        <div class="season-months-picker" style="display: none;">
            <div class="season-shortcuts">
                <button type="button" class="btn-season-preset" data-preset="spring">🌱 Printemps (Mar-Mai)</button>
                <button type="button" class="btn-season-preset" data-preset="summer">☀️ Été (Juin-Aoû)</button>
                <button type="button" class="btn-season-preset" data-preset="autumn">🍁 Automne (Sep-Nov)</button>
                <button type="button" class="btn-season-preset" data-preset="winter">❄️ Hiver (Déc-Fév)</button>
                <button type="button" class="btn-season-preset" data-preset="all">Tout cocher</button>
                <button type="button" class="btn-season-preset" data-preset="clear">Tout décocher</button>
            </div>
            <div class="season-months-grid"></div>
        </div>
        <div class="season-unknown-alert" style="display: none;">
            ⚠️ <strong>Avertissement :</strong> Cet ingrédient sera temporairement considéré comme disponible toute l'année. Un message d'avertissement sera consigné et transmis à l'administrateur / backend pour qu'il recherche et renseigne manuellement ses mois de récolte.
        </div>
    `;

    // Populate month chips (1-12)
    const monthsGrid = seasonBox.querySelector(".season-months-grid");
    const monthNames = [
        { num: 1, label: "Jan" },
        { num: 2, label: "Fév" },
        { num: 3, label: "Mar" },
        { num: 4, label: "Avr" },
        { num: 5, label: "Mai" },
        { num: 6, label: "Juin" },
        { num: 7, label: "Juil" },
        { num: 8, label: "Aoû" },
        { num: 9, label: "Sep" },
        { num: 10, label: "Oct" },
        { num: 11, label: "Nov" },
        { num: 12, label: "Déc" },
    ];
    monthNames.forEach((m) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "month-chip";
        chip.textContent = m.label;
        chip.setAttribute("data-month", m.num);
        chip.addEventListener("click", () => {
            chip.classList.toggle("active");
        });
        monthsGrid.appendChild(chip);
    });

    const monthsPicker = seasonBox.querySelector(".season-months-picker");
    const unknownAlert = seasonBox.querySelector(".season-unknown-alert");

    // Handle radio changes
    seasonBox.querySelectorAll(`input[name="season-mode-${rowSeasonId}"]`).forEach((radio) => {
        radio.addEventListener("change", (e) => {
            const mode = e.target.value;
            monthsPicker.style.display = mode === "custom_months" ? "flex" : "none";
            unknownAlert.style.display = mode === "unknown" ? "block" : "none";
        });
    });

    // Preset shortcuts handlers
    seasonBox.querySelectorAll(".btn-season-preset").forEach((btn) => {
        btn.addEventListener("click", () => {
            const preset = btn.getAttribute("data-preset");
            const allChips = seasonBox.querySelectorAll(".month-chip");
            allChips.forEach((chip) => {
                const m = parseInt(chip.getAttribute("data-month"), 10);
                if (preset === "all") chip.classList.add("active");
                else if (preset === "clear") chip.classList.remove("active");
                else if (preset === "spring") chip.classList.toggle("active", [3, 4, 5].includes(m));
                else if (preset === "summer") chip.classList.toggle("active", [6, 7, 8].includes(m));
                else if (preset === "autumn") chip.classList.toggle("active", [9, 10, 11].includes(m));
                else if (preset === "winter") chip.classList.toggle("active", [12, 1, 2].includes(m));
            });
        });
    });

    // Main ingredient fields row
    const row = document.createElement("div");
    row.className = "ingredient-form-row";

    // Ingredient name input (free-text with existing ingredients datalist)
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "form-input ing-name";
    nameInput.placeholder = "Ingrédient (ex: Carotte, Poulet...)";
    nameInput.setAttribute("list", "existing-substitutes-datalist");
    nameInput.required = true;

    // Ingredient family / category select
    const categorySelect = document.createElement("select");
    categorySelect.className = "form-input ing-category";
    categorySelect.title = "Famille d'ingrédient";

    const categoriesList = [
        { value: "légume", label: "🥦 Légume" },
        { value: "champignon", label: "🍄 Champignon" },
        { value: "fruit", label: "🍎 Fruit" },
        { value: "féculent", label: "🍝 Féculent" },
        { value: "légumineuse", label: "🫘 Légumineuse" },
        { value: "protéine", label: "🥚 Protéine" },
        { value: "viande", label: "🥩 Viande" },
        { value: "poisson", label: "🐟 Poisson" },
        { value: "produit laitier", label: "🥛 Produit laitier" },
        { value: "fromage", label: "🧀 Fromage" },
        { value: "matière grasse", label: "🧈 Matière grasse" },
        { value: "herbe/épice", label: "🌿 Herbe / Épice" },
        { value: "condiment", label: "🧂 Condiment" },
        { value: "produit sucré", label: "🍯 Produit sucré" },
        { value: "produit végétal", label: "🌱 Produit végétal" },
        { value: "autre", label: "📦 Autre" },
    ];
    categoriesList.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.value;
        opt.textContent = c.label;
        categorySelect.appendChild(opt);
    });

    // Auto-detect category and toggle seasonality panel for brand new ingredients
    function checkNewIngredientSeasonality() {
        const val = nameInput.value.trim().toLowerCase();
        const matched = state.allIngredients.find(
            (i) => i.name.toLowerCase() === val
        );
        if (matched) {
            categorySelect.value = matched.category;
            categorySelect.disabled = true;
            categorySelect.title = "Famille d'ingrédient déjà définie dans le catalogue (non modifiable)";
            seasonBox.style.display = "none";
        } else if (val.length >= 2) {
            categorySelect.disabled = false;
            categorySelect.title = "Famille d'ingrédient";
            seasonBox.style.display = "flex";
            const targetName = seasonBox.querySelector(".season-target-name");
            if (targetName) targetName.textContent = `« ${nameInput.value.trim()} »`;
        } else {
            categorySelect.disabled = false;
            categorySelect.title = "Famille d'ingrédient";
            seasonBox.style.display = "none";
        }
    }
    nameInput.addEventListener("input", checkNewIngredientSeasonality);
    nameInput.addEventListener("change", checkNewIngredientSeasonality);

    // Quantity input (classic direct text input without dropdowns or spinner arrows)
    const qtyInput = document.createElement("input");
    qtyInput.type = "text";
    qtyInput.inputMode = "decimal";
    qtyInput.value = "100";
    qtyInput.placeholder = "Qté (ex: 100, 2.5)";
    qtyInput.className = "form-input ing-qty";
    qtyInput.autocomplete = "off";
    qtyInput.required = true;

    // Unit input
    const unitInput = document.createElement("input");
    unitInput.type = "text";
    unitInput.value = "g";
    unitInput.placeholder = "g, ml...";
    unitInput.className = "form-input ing-unit";
    unitInput.required = true;

    // Importance select
    const impSelect = document.createElement("select");
    impSelect.className = "form-input ing-imp";
    impSelect.innerHTML = `
        <option value="3">3 - Indispensable</option>
        <option value="2" selected>2 - Majeur</option>
        <option value="1">1 - Optionnel</option>
    `;

    // Remove row button
    const btnRemove = document.createElement("button");
    btnRemove.type = "button";
    btnRemove.className = "btn-remove-row";
    btnRemove.textContent = "✕";
    btnRemove.title = "Supprimer cet ingrédient";
    btnRemove.addEventListener("click", () => {
        item.remove();
    });

    row.appendChild(nameInput);
    row.appendChild(categorySelect);
    row.appendChild(qtyInput);
    row.appendChild(unitInput);
    row.appendChild(impSelect);
    row.appendChild(btnRemove);

    if (data) {
        nameInput.value = data.name || "";
        qtyInput.value = data.quantity !== undefined ? data.quantity : "100";
        unitInput.value = data.unit || "g";
        if (data.importance) impSelect.value = String(data.importance);
        checkNewIngredientSeasonality();
    }

    item.appendChild(row);
    item.appendChild(seasonBox);
    container.appendChild(item);
}

/**
 * Add an instruction step row in the recipe creation form.
 */
function addStepRow(initialText = "") {
    const container = document.getElementById("new-recipe-steps-list");
    if (!container) return;

    const row = document.createElement("div");
    row.className = "step-form-row";

    const badge = document.createElement("span");
    badge.className = "step-number-badge";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-input step-text";
    input.value = initialText;
    input.placeholder = "Détaillez cette étape (ex: Préchauffer le four à 180°C)...";
    input.required = true;

    const btnRemove = document.createElement("button");
    btnRemove.type = "button";
    btnRemove.className = "btn-remove-step";
    btnRemove.textContent = "✕";
    btnRemove.title = "Supprimer cette étape";
    btnRemove.addEventListener("click", () => {
        // Keep at least one step row
        if (container.children.length > 1) {
            row.remove();
            renumberSteps();
        } else {
            input.value = "";
        }
    });

    row.appendChild(badge);
    row.appendChild(input);
    row.appendChild(btnRemove);
    container.appendChild(row);

    renumberSteps();
    return input;
}

/**
 * Renumber all step badges sequentially.
 */
function renumberSteps() {
    const badges = document.querySelectorAll("#new-recipe-steps-list .step-number-badge");
    badges.forEach((b, idx) => {
        b.textContent = idx + 1;
    });
}

/**
 * Format raw recipe instructions into an HTML bulleted list.
 */
function formatInstructionsHtml(instructions) {
    if (!instructions) return "<em>Aucune instruction indiquée.</em>";

    let steps = [];

    // Check if instructions already have newlines or bullet points
    if (instructions.includes("\n") || instructions.includes("•") || instructions.includes("- ")) {
        steps = instructions
            .split(/\r?\n|•/)
            .map((s) => s.replace(/^[-*]\s*/, "").trim())
            .filter((s) => s.length > 0);
    } else {
        // Fallback: split continuous sentences on periods
        steps = instructions
            .split(/\.\s+/)
            .map((s) => s.trim().replace(/\.$/, ""))
            .filter((s) => s.length > 0);
    }

    if (steps.length === 0) {
        return `<p>${instructions}</p>`;
    }

    const itemsHtml = steps.map((s) => `<li>${s}</li>`).join("");
    return `<ul class="instructions-steps-list">${itemsHtml}</ul>`;
}

/**
 * Render datalist suggestions for existing ingredients.
 */
function renderDatalist() {
    let dl = document.getElementById("existing-substitutes-datalist");
    if (!dl) {
        dl = document.createElement("datalist");
        dl.id = "existing-substitutes-datalist";
        document.body.appendChild(dl);
    }
    dl.innerHTML = "";
    state.allIngredients.forEach((ing) => {
        const opt = document.createElement("option");
        opt.value = ing.name;
        dl.appendChild(opt);
    });
}

/**
 * Reload pantry ingredients from backend.
 */
async function reloadIngredients() {
    try {
        const res = await fetch("/api/ingredients");
        if (res.ok) {
            state.allIngredients = await res.json();
            renderIngredients();
            renderDatalist();
            renderSeasonCalendar();
        }
    } catch (err) {
        console.error("Failed to reload ingredients:", err);
    }
}

/**
 * Populate dropdown of existing recipes for alternative recipe selection.
 */
async function populateParentRecipeDropdown() {
    const select = document.getElementById("new-recipe-parent-id");
    if (!select || !state.activeAccountId) return;

    select.innerHTML = '<option value="">Chargement de vos recettes...</option>';
    try {
        const res = await fetch(`/api/accounts/${state.activeAccountId}/recipes`);
        if (res.ok) {
            const recipes = await res.json();
            select.innerHTML = '<option value="">-- Sélectionner la recette originale --</option>';
            if (recipes.length === 0) {
                select.innerHTML = '<option value="">Aucune recette existante dans ce compte</option>';
                return;
            }
            recipes.forEach((rec) => {
                if (state.editingRecipeId && rec.recipe_id === state.editingRecipeId) return;
                const opt = document.createElement("option");
                opt.value = rec.recipe_id;
                const authorNote = rec.is_own ? "" : ` (partagée par ${rec.author_name})`;
                opt.textContent = `${rec.title}${rec.is_alternative ? " (Alternative)" : ""}${authorNote}`;
                select.appendChild(opt);
            });
        } else {
            select.innerHTML = '<option value="">Erreur de chargement</option>';
        }
    } catch (err) {
        console.error("Failed to load recipes for parent selector:", err);
        select.innerHTML = '<option value="">Erreur de chargement</option>';
    }
}

/**
 * Reset recipe form to create mode (clean inputs, default labels).
 */
function resetRecipeFormToCreateMode() {
    state.editingRecipeId = null;
    const form = document.getElementById("create-recipe-form");
    if (form) form.reset();

    const titleEl = document.getElementById("create-recipe-view-title");
    const descEl = document.getElementById("create-recipe-view-desc");
    const submitBtn = document.getElementById("btn-submit-recipe");
    if (titleEl) titleEl.textContent = "Créer une nouvelle recette";
    if (descEl) descEl.textContent = "Remplissez les informations ci-dessous pour ajouter une recette à votre carnet personnel.";
    if (submitBtn) submitBtn.textContent = "Enregistrer la recette";

    const isAltCheckbox = document.getElementById("new-recipe-is-alternative");
    const altSelectBox = document.getElementById("alternative-recipe-select-box");
    if (isAltCheckbox) isAltCheckbox.checked = false;
    if (altSelectBox) altSelectBox.style.display = "none";

    const list = document.getElementById("new-recipe-ingredients-list");
    if (list) {
        list.innerHTML = "";
        addIngredientRow();
    }
    const stepsList = document.getElementById("new-recipe-steps-list");
    if (stepsList) {
        stepsList.innerHTML = "";
        addStepRow();
        addStepRow();
    }
}

/**
 * Open recipe creation form pre-filled in edit mode for an authored recipe.
 * @param {Object} rec - Recipe recommendation/detail object
 */
async function openEditRecipeForm(rec) {
    if (!rec || !rec.is_own) {
        showToast("Vous ne pouvez modifier que les recettes dont vous êtes l'auteur.");
        return;
    }

    state.editingRecipeId = rec.recipe_id;

    // Switch view to form
    switchView("view-create-recipe");

    // Update headers and submit button text
    const titleEl = document.getElementById("create-recipe-view-title");
    const descEl = document.getElementById("create-recipe-view-desc");
    const submitBtn = document.getElementById("btn-submit-recipe");
    if (titleEl) titleEl.textContent = `✏️ Modifier la recette : ${rec.title}`;
    if (descEl) descEl.textContent = "Modifiez les ingrédients, portions ou étapes ci-dessous.";
    if (submitBtn) submitBtn.textContent = "Enregistrer les modifications";

    // Fill basic form inputs
    const titleInput = document.getElementById("new-recipe-title");
    if (titleInput) titleInput.value = rec.title;
    const visInput = document.getElementById("new-recipe-visibility");
    if (visInput) visInput.value = rec.visibility;
    const freezableInput = document.getElementById("new-recipe-freezable");
    if (freezableInput) freezableInput.value = rec.is_freezable ? "true" : "false";
    const prepInput = document.getElementById("new-recipe-prep");
    if (prepInput) prepInput.value = rec.prep_time_minutes;
    const cookInput = document.getElementById("new-recipe-cook");
    if (cookInput) cookInput.value = rec.cook_time_minutes;
    const servingsInput = document.getElementById("new-recipe-servings");
    if (servingsInput) servingsInput.value = rec.servings;

    // Alternative configuration
    const isAltCheckbox = document.getElementById("new-recipe-is-alternative");
    const altSelectBox = document.getElementById("alternative-recipe-select-box");
    const parentSelect = document.getElementById("new-recipe-parent-id");
    if (rec.is_alternative && rec.parent_recipe_id) {
        if (isAltCheckbox) isAltCheckbox.checked = true;
        if (altSelectBox) altSelectBox.style.display = "block";
        await populateParentRecipeDropdown();
        if (parentSelect) parentSelect.value = String(rec.parent_recipe_id);
    } else {
        if (isAltCheckbox) isAltCheckbox.checked = false;
        if (altSelectBox) altSelectBox.style.display = "none";
    }

    // Populate ingredient rows (locking existing category)
    const list = document.getElementById("new-recipe-ingredients-list");
    if (list) {
        list.innerHTML = "";
        (rec.ingredients || []).forEach((ing) => {
            addIngredientRow({
                name: ing.name,
                category: ing.category,
                quantity: ing.quantity,
                unit: ing.unit,
                importance: ing.importance,
            });
        });
        if (list.children.length === 0) {
            addIngredientRow();
        }
    }

    // Populate instruction steps
    const stepsList = document.getElementById("new-recipe-steps-list");
    if (stepsList) {
        stepsList.innerHTML = "";
        const lines = (rec.instructions || "")
            .split("\n")
            .map((l) => l.replace(/^[•\-\*\d\.\s]+/, "").trim())
            .filter((l) => l.length > 0);
        if (lines.length > 0) {
            lines.forEach((l) => addStepRow(l));
        } else {
            addStepRow(rec.instructions || "");
        }
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
}

/**
 * Handle submission of recipe creation form.
 */
async function handleCreateRecipeSubmit(e) {
    e.preventDefault();
    if (!state.activeAccountId) {
        showToast("Impossible de créer une recette en mode invité.");
        return;
    }

    const title = document.getElementById("new-recipe-title").value.trim();
    const visibility = document.getElementById("new-recipe-visibility").value;
    const isFreezable = document.getElementById("new-recipe-freezable")?.value === "true";
    const prep = parseInt(document.getElementById("new-recipe-prep").value, 10) || 15;
    const cook = parseInt(document.getElementById("new-recipe-cook").value, 10) || 20;
    const servings = parseInt(document.getElementById("new-recipe-servings").value, 10) || 4;

    const isAlt = document.getElementById("new-recipe-is-alternative")?.checked || false;
    let parentRecipeId = null;
    if (isAlt) {
        const pVal = document.getElementById("new-recipe-parent-id")?.value;
        if (!pVal) {
            showToast("Veuillez sélectionner la recette originale de référence.");
            return;
        }
        parentRecipeId = parseInt(pVal, 10);
    }

    // Gather instructions steps
    const stepInputs = document.querySelectorAll("#new-recipe-steps-list .step-text");
    const steps = [];
    stepInputs.forEach((inp) => {
        const val = inp.value.trim();
        if (val) steps.push(val);
    });

    if (steps.length === 0) {
        showToast("Veuillez indiquer au moins une étape de préparation.");
        return;
    }

    const instructions = steps.map((s) => `• ${s}`).join("\n");

    const items = document.querySelectorAll(".ingredient-form-item");
    const ingredients = [];

    items.forEach((item) => {
        const nameVal = item.querySelector(".ing-name")?.value.trim() || "";
        const catVal = item.querySelector(".ing-category")?.value || "autre";
        const rawQty = (item.querySelector(".ing-qty")?.value || "").replace(",", ".");
        const qty = parseFloat(rawQty);
        const unit = item.querySelector(".ing-unit")?.value.trim() || "g";
        const imp = parseInt(item.querySelector(".ing-imp")?.value, 10) || 2;

        // Check if nameVal matches existing ingredient
        const matched = state.allIngredients.find(
            (i) => i.name.toLowerCase() === nameVal.toLowerCase()
        );

        let availableMonths = null;
        let seasonUnknown = false;

        const seasonBox = item.querySelector(".seasonality-form-box");
        if (!matched && seasonBox && seasonBox.style.display !== "none") {
            const checkedRadio = seasonBox.querySelector("input[type='radio']:checked");
            const mode = checkedRadio ? checkedRadio.value : "all_year";

            if (mode === "unknown") {
                seasonUnknown = true;
                availableMonths = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
            } else if (mode === "custom_months") {
                const activeMonthChips = seasonBox.querySelectorAll(".month-chip.active");
                availableMonths = Array.from(activeMonthChips)
                    .map((c) => parseInt(c.getAttribute("data-month"), 10))
                    .sort((a, b) => a - b);
                if (availableMonths.length === 0) {
                    availableMonths = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
                }
            } else {
                availableMonths = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
            }
        }

        if (nameVal && qty > 0) {
            ingredients.push({
                ingredient_id: matched ? matched.id : null,
                name: nameVal,
                category: catVal,
                quantity: qty,
                unit: unit,
                importance: imp,
                available_months: availableMonths,
                season_unknown: seasonUnknown,
            });
        }
    });

    if (ingredients.length === 0) {
        showToast("Veuillez ajouter au moins un ingrédient.");
        return;
    }

    const payload = {
        account_id: state.activeAccountId,
        title: title,
        instructions: instructions,
        prep_time_minutes: prep,
        cook_time_minutes: cook,
        base_servings: servings,
        is_freezable: isFreezable,
        visibility: visibility,
        parent_recipe_id: parentRecipeId,
        ingredients: ingredients
    };

    const isEditing = !!state.editingRecipeId;
    const url = isEditing ? `/api/recipes/${state.editingRecipeId}` : "/api/recipes";
    const method = isEditing ? "PUT" : "POST";

    try {
        const res = await fetch(url, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            if (isEditing) {
                showToast(`Recette "${title}" modifiée avec succès !`);
            } else if (ingredients.some((i) => i.season_unknown)) {
                showToast(`Recette "${title}" enregistrée ! Un avertissement a été transmis à l'administrateur pour la saisonnalité.`);
            } else {
                showToast(`Recette "${title}" enregistrée avec succès !`);
            }
            resetRecipeFormToCreateMode();
            await reloadIngredients();
            switchView("view-my-recipes");
        } else {
            const err = await res.json();
            showToast(`Erreur : ${err.detail || "Impossible d'enregistrer"}`);
        }
    } catch (error) {
        console.error("Recipe save error:", error);
        showToast("Erreur réseau lors de l'enregistrement de la recette.");
    }
}

/**
 * Render pantry ingredients grouped by category with active state and search filtering.
 */
function renderIngredients() {
    const container = document.getElementById("ingredients-container");
    if (!container) return;

    const filtered = state.allIngredients.filter((ing) => {
        if (!state.filterQuery) return true;
        return (
            ing.name.toLowerCase().includes(state.filterQuery) ||
            ing.category.toLowerCase().includes(state.filterQuery)
        );
    });

    if (filtered.length === 0) {
        container.innerHTML = `<div class="empty-state">Aucun ingrédient correspondant à "${state.filterQuery}"</div>`;
        return;
    }

    const categories = {};
    filtered.forEach((ing) => {
        if (!categories[ing.category]) {
            categories[ing.category] = [];
        }
        categories[ing.category].push(ing);
    });

    container.innerHTML = "";
    Object.keys(categories).sort().forEach((cat) => {
        const group = document.createElement("div");
        group.className = "category-group";

        const title = document.createElement("div");
        title.className = "category-title";
        title.textContent = cat;
        group.appendChild(title);

        const chipContainer = document.createElement("div");
        chipContainer.className = "chip-container";

        categories[cat].forEach((ing) => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = `chip ${state.selectedIngredientIds.has(ing.id) ? "active" : ""}`;
            chip.textContent = ing.name;

            chip.addEventListener("click", () => {
                if (state.selectedIngredientIds.has(ing.id)) {
                    state.selectedIngredientIds.delete(ing.id);
                } else {
                    state.selectedIngredientIds.add(ing.id);
                }
                chip.classList.toggle("active", state.selectedIngredientIds.has(ing.id));
                updateSelectedSummary();
                triggerSearch();
            });

            chipContainer.appendChild(chip);
        });

        group.appendChild(chipContainer);
        container.appendChild(group);
    });

    updateSelectedSummary();
}

/**
 * Update summary label showing count of selected ingredients.
 */
function updateSelectedSummary() {
    const summary = document.getElementById("selected-summary");
    if (summary) {
        const count = state.selectedIngredientIds.size;
        summary.textContent = `${count} ingrédient(s) sélectionné(s)`;
    }
}

/**
 * Send search request to backend API and render resulting recipes.
 */
async function triggerSearch() {
    const resultsContainer = document.getElementById("recipes-list");
    const countSpan = document.getElementById("results-count");

    if (state.selectedIngredientIds.size === 0) {
        state.searchRecipes = [];
        applyRecipeFilters("search");
        return;
    }

    try {
        const payload = {
            account_id: state.activeAccountId,
            include_public: state.includePublic,
            profile_ids: Array.from(state.selectedProfileIds),
            ingredient_ids: Array.from(state.selectedIngredientIds),
            target_servings: state.servings,
            min_match_score: 0.0
        };

        const response = await fetch("/api/recipes/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }

        state.searchRecipes = await response.json();
        applyRecipeFilters("search");
    } catch (error) {
        console.error("Search request failed:", error);
        if (resultsContainer) {
            resultsContainer.innerHTML = `
                <div class="empty-state text-danger">
                    Erreur lors de la recherche des recettes. Vérifiez la connexion API.
                </div>
            `;
        }
    }
}

const ALLERGEN_ICONS = {
    gluten: "🌾",
    crustaces: "🦐",
    oeufs: "🥚",
    poissons: "🐟",
    arachides: "🥜",
    soja: "🫘",
    lait: "🥛",
    fruits_a_coque: "🌰",
    celeri: "🥬",
    moutarde: "🫙",
    sesame: "🥯",
    sulfites: "🍷",
    lupin: "🌼",
    mollusques: "🦪",
};

/**
 * Render allergen icon badges with hover tooltips for a recipe's allergen slugs.
 */
function renderRecipeAllergenIcons(allergenSlugs) {
    if (!allergenSlugs || allergenSlugs.length === 0) return "";
    const labelMap = new Map(state.allAllergens.map((a) => [a.name, a.label]));
    const badges = allergenSlugs.map((slug) => {
        const icon = ALLERGEN_ICONS[slug] || "⚠️";
        const label = (labelMap.get(slug) || slug).replace(/"/g, "&quot;");
        return `<span class="allergen-icon-badge" data-tooltip="Allergène : ${label}" title="Allergène : ${label}" aria-label="Allergène : ${label}">${icon}</span>`;
    });
    return `<span class="recipe-allergen-icons">${badges.join("")}</span>`;
}

/**
 * Build and render HTML cards for recipe list.
 * @param {Array} recipes - Array of recipe objects
 * @param {string} targetContainerId - DOM element id to render cards in
 * @param {boolean} showMatchScore - Whether to display compatibility score pill
 */
function renderRecipeCards(recipes, targetContainerId = "recipes-list", showMatchScore = true) {
    const container = document.getElementById(targetContainerId);
    if (!container) return;

    if (recipes.length === 0) {
        container.innerHTML = `<div class="empty-state">Aucune recette ne contient ces ingrédients. Essayez d'en sélectionner d'autres !</div>`;
        return;
    }

    container.innerHTML = "";
    recipes.forEach((rec) => {
        // Cache recipe in state map so it can be retrieved for full detail page display
        state.loadedRecipesMap.set(rec.recipe_id, rec);

        // Check if recipe is alternative or original with alternatives
        let alternativePill = "";
        if (rec.is_alternative) {
            const parentName = rec.parent_recipe_title || "";
            const pillText = parentName ? `🔄 Alternative de ${parentName}` : "🔄 Alternative";
            const tooltip = parentName ? `Recette alternative de : ${parentName}`.replace(/"/g, '&quot;') : "Recette alternative";
            alternativePill = `<span class="pill-visibility pill-alternative" title="${tooltip}">${pillText}</span>`;
        } else if (rec.has_alternatives) {
            alternativePill = `<span class="pill-visibility pill-original" title="Recette originale de référence (possède des variantes alternatives)">✨ Recette originale</span>`;
        }

        const card = document.createElement("article");
        card.className = `recipe-card ${rec.has_veto ? "has-veto" : ""}`.trim();

        // Compatibility score class
        let scorePillHtml = "";
        if (showMatchScore) {
            let scoreClass = "score-low";
            if (rec.match_score >= 80) scoreClass = "score-high";
            else if (rec.match_score >= 50) scoreClass = "score-mid";

            scorePillHtml = `
                <div class="score-pill ${scoreClass}">
                    ${rec.match_score}%
                    <span>Match</span>
                </div>
            `;
        }

        // Veto banner if applicable
        let vetoHtml = "";
        if (rec.has_veto && rec.veto_reasons.length > 0) {
            vetoHtml = `
                <div class="veto-banner">
                    <span>⚠️</span>
                    <span>Attention : ${rec.veto_reasons.join(", ")}</span>
                </div>
            `;
        }

        // Visibility pill
        let visibilityPill = "";
        if (rec.is_own) {
            visibilityPill = rec.visibility === "public"
                ? `<span class="pill-visibility pill-public">🌐 Publique </span>`
                : `<span class="pill-visibility pill-private">🔒 Privée </span>`;
            if (rec.shared_with && rec.shared_with.length > 0) {
                visibilityPill += ` <span class="pill-visibility pill-shared">🤝 Partagée avec ${rec.shared_with.join(", ")}</span>`;
            }
        } else if (rec.visibility === "public") {
            visibilityPill = `<span class="pill-visibility pill-public">🌐 Publique </span>`;
        } else {
            visibilityPill = `<span class="pill-visibility pill-shared">🤝 Partagée par ${rec.author_name}</span>`;
        }

        // Seasonality badge
        const seasonBadge = rec.seasonality_score === 100
            ? `<span class="badge badge-success">🌱 100% de saison</span>`
            : `<span class="badge badge-warning">🌱 ${rec.seasonality_score}% de saison</span>`;

        // Ingredients rows
        const ingredientsHtml = rec.ingredients.map((ing) => {
            let statusIcon = "";
            let statusClass = "";

            if (showMatchScore) {
                if (ing.status === "available") {
                    statusIcon = "✓";
                    statusClass = "status-available";
                } else {
                    statusIcon = "✕";
                    statusClass = "status-missing";
                }
            } else {
                statusIcon = "•";
                statusClass = "status-available";
            }

            let impLabel = "Optionnel";
            let impClass = "";
            if (ing.importance === 3) {
                impLabel = "Indispensable";
                impClass = "importance-essential";
            } else if (ing.importance === 2) {
                impLabel = "Majeur";
            }

            return `
                <div>
                    <div class="ingredient-row">
                        <div class="ingredient-name-col">
                            <span class="status-icon ${statusClass}">${statusIcon}</span>
                            <span class="${showMatchScore && ing.status === 'missing' ? 'text-muted' : ''}">${ing.name}</span>
                            <span class="importance-badge ${impClass}">${impLabel}</span>
                        </div>
                        <div>
                            <strong>${ing.quantity} ${ing.unit}</strong>
                        </div>
                    </div>
                </div>
            `;
        }).join("");

        // Sharing actions row
        let actionsRow = `
            <div class="recipe-actions-row">
                <button type="button" class="btn-secondary btn-sm btn-copy-link" data-token="${rec.share_token}">
                    🔗 Copier le lien de partage
                </button>
        `;

        if (rec.is_own) {
            const nextVisibility = rec.visibility === "public" ? "private" : "public";
            const toggleLabel = rec.visibility === "public" ? "Rendre privée 🔒" : "Rendre publique 🌐";

            // Exclude already shared accounts
            const shareableAccounts = state.allAccounts.filter(a =>
                a.id !== state.activeAccountId &&
                !(rec.shared_with_ids && rec.shared_with_ids.includes(a.id)) &&
                !(rec.shared_with && rec.shared_with.includes(a.display_name))
            );

            let shareSelectHtml = "";
            if (shareableAccounts.length > 0) {
                shareSelectHtml = `
                    <select class="account-dropdown select-share-account" data-id="${rec.recipe_id}">
                        <option value="">Partager avec...</option>
                        ${shareableAccounts.map(a => `<option value="${a.id}">Partager avec ${a.display_name}</option>`).join("")}
                    </select>
                `;
            } else {
                shareSelectHtml = `
                    <select class="account-dropdown select-share-account" data-id="${rec.recipe_id}" disabled title="Déjà partagée avec tous vos proches">
                        <option value="">✓ Déjà partagée avec tous vos proches</option>
                    </select>
                `;
            }

            actionsRow += `
                <div class="sharing-buttons-group">
                    <button type="button" class="btn-secondary btn-sm btn-edit-recipe" data-id="${rec.recipe_id}">
                        ✏️ Modifier
                    </button>
                    <button type="button" class="btn-secondary btn-sm btn-toggle-vis" data-id="${rec.recipe_id}" data-next="${nextVisibility}">
                        ${toggleLabel}
                    </button>
                    ${shareSelectHtml}
                </div>
            `;
        }

        actionsRow += `</div>`;

        const allergenIconsHtml = renderRecipeAllergenIcons(rec.allergens);
        const freezablePillHtml = rec.is_freezable
            ? `<span class="pill-freezable">❄️ Congélable</span>`
            : "";
        const rightHeaderHtml = (freezablePillHtml || scorePillHtml)
            ? `<div class="recipe-card-header-right">${freezablePillHtml}${scorePillHtml}</div>`
            : "";

        card.innerHTML = `
            ${vetoHtml}
            <div class="recipe-card-header">
                <div>
                    <div class="recipe-title-row">
                        <h4 class="recipe-title"><a href="javascript:void(0)" class="recipe-title-link" data-recipe-id="${rec.recipe_id}">${rec.title}</a></h4>
                        ${alternativePill}
                        ${visibilityPill}
                        ${allergenIconsHtml}
                    </div>
                    <div class="recipe-meta">
                        <span>⏱️ Prépa : ${rec.prep_time_minutes} min</span>
                        <span>🔥 Cuisson : ${rec.cook_time_minutes} min</span>
                        <span>🍽️ Portions : ${rec.servings} pers.</span>
                        ${seasonBadge}
                    </div>
                </div>
                ${rightHeaderHtml}
            </div>

            <div class="recipe-ingredients-list">
                ${ingredientsHtml}
            </div>

            <details class="recipe-details-toggle">
                <summary>Voir les étapes de préparation</summary>
                <div class="recipe-instructions">${formatInstructionsHtml(rec.instructions)}</div>
            </details>

            ${actionsRow}
        `;

        container.appendChild(card);
    });

    // Attach listeners to newly created action buttons
    attachCardActionListeners(targetContainerId);
}

/**
 * Attach event listeners to card buttons (copy link, toggle visibility, share with account, open detail).
 */
function attachCardActionListeners(containerId) {
    const parent = document.getElementById(containerId);
    if (!parent) return;

    // Click recipe title to open recipe detail page
    parent.querySelectorAll(".recipe-title-link").forEach((link) => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            const id = parseInt(link.getAttribute("data-recipe-id"), 10);
            const rec = state.loadedRecipesMap.get(id);
            if (rec) {
                openRecipeDetailPage(rec);
            }
        });
    });

    // Edit recipe button
    parent.querySelectorAll(".btn-edit-recipe").forEach((btn) => {
        btn.addEventListener("click", () => {
            const recipeId = parseInt(btn.getAttribute("data-id"), 10);
            const rec = state.loadedRecipesMap.get(recipeId);
            if (rec) {
                openEditRecipeForm(rec);
            }
        });
    });

    // Option C: Copy share link
    parent.querySelectorAll(".btn-copy-link").forEach((btn) => {
        btn.addEventListener("click", () => {
            const token = btn.getAttribute("data-token");
            const shareUrl = `${window.location.origin}/?share=${encodeURIComponent(token)}`;
            navigator.clipboard.writeText(shareUrl).then(() => {
                showToast("Lien de partage copié dans le presse-papier !");
            }).catch(() => {
                prompt("Copiez ce lien pour partager la recette :", shareUrl);
            });
        });
    });

    // Option A: Toggle public / private
    parent.querySelectorAll(".btn-toggle-vis").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const recipeId = parseInt(btn.getAttribute("data-id"), 10);
            const nextVis = btn.getAttribute("data-next");
            try {
                const res = await fetch(`/api/recipes/${recipeId}/visibility?visibility=${nextVis}`, {
                    method: "POST"
                });
                if (res.ok) {
                    showToast(`Recette passée en ${nextVis === "public" ? "publique" : "privée"}.`);
                    const cached = state.loadedRecipesMap.get(recipeId);
                    if (cached) {
                        cached.visibility = nextVis;
                    }
                    if (state.currentView === "view-recipe-detail" && cached) {
                        renderRecipeDetailContent(cached);
                    } else if (state.currentView === "view-my-recipes") {
                        loadAccountRecipes();
                    } else {
                        triggerSearch();
                    }
                }
            } catch (err) {
                console.error("Visibility toggle failed:", err);
            }
        });
    });

    // Option B: Share with target account
    parent.querySelectorAll(".select-share-account").forEach((sel) => {
        sel.addEventListener("change", async (e) => {
            const recipeId = sel.getAttribute("data-id");
            const targetId = parseInt(e.target.value, 10);
            if (!targetId) return;

            try {
                const res = await fetch(`/api/recipes/${recipeId}/share`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ target_account_id: targetId })
                });
                if (res.ok) {
                    const data = await res.json();
                    showToast(data.message || "Recette partagée avec succès !");
                    if (state.currentView === "view-my-recipes") {
                        loadAccountRecipes();
                    } else {
                        triggerSearch();
                    }
                }
            } catch (err) {
                console.error("Share failed:", err);
            }
            sel.value = "";
        });
    });
}

/**
 * Switch view to recipe detail page and render the full recipe.
 * @param {Object} rec - The recipe recommendation or detail object
 */
function openRecipeDetailPage(rec) {
    if (!rec) return;

    state.previousView = state.currentView;
    state.currentView = "view-recipe-detail";

    // Toggle view sections
    document.querySelectorAll(".app-view").forEach((view) => {
        view.style.display = view.id === "view-recipe-detail" ? "block" : "none";
    });

    // Unselect navigation tabs
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.classList.remove("active");
    });

    renderRecipeDetailContent(rec);
    window.scrollTo({ top: 0, behavior: "smooth" });
}

/**
 * Render the full recipe detail into #recipe-detail-container.
 * @param {Object} rec - The recipe object
 */
function renderRecipeDetailContent(rec) {
    const container = document.getElementById("recipe-detail-container");
    if (!container) return;

    let alternativePill = "";
    if (rec.is_alternative) {
        const parentName = rec.parent_recipe_title || "";
        const pillText = parentName ? `🔄 Alternative de ${parentName}` : "🔄 Alternative";
        const tooltip = parentName ? `Recette alternative de : ${parentName}`.replace(/"/g, '&quot;') : "Recette alternative";
        alternativePill = `<span class="pill-visibility pill-alternative" title="${tooltip}">${pillText}</span>`;
    } else if (rec.has_alternatives) {
        alternativePill = `<span class="pill-visibility pill-original" title="Recette originale de référence (possède des variantes alternatives)">✨ Recette originale</span>`;
    }

    container.className = "recipe-detail-card card";

    // Compatibility score pill
    let scorePillHtml = "";
    if (rec.match_score !== undefined && rec.match_score !== null) {
        let scoreClass = "score-low";
        if (rec.match_score >= 80) scoreClass = "score-high";
        else if (rec.match_score >= 50) scoreClass = "score-mid";

        scorePillHtml = `
            <div class="score-pill ${scoreClass}">
                ${rec.match_score}%
                <span>Match</span>
            </div>
        `;
    }

    // Veto banner if applicable
    let vetoHtml = "";
    if (rec.has_veto && rec.veto_reasons && rec.veto_reasons.length > 0) {
        vetoHtml = `
            <div class="veto-banner">
                <span>⚠️</span>
                <span>Attention : ${rec.veto_reasons.join(", ")}</span>
            </div>
        `;
    }

    // Visibility pill
    let visibilityPill = "";
    if (rec.is_own) {
        visibilityPill = rec.visibility === "public"
            ? `<span class="pill-visibility pill-public">🌐 Publique</span>`
            : `<span class="pill-visibility pill-private">🔒 Privée</span>`;
        if (rec.shared_with && rec.shared_with.length > 0) {
            visibilityPill += ` <span class="pill-visibility pill-shared">🤝 Partagée avec ${rec.shared_with.join(", ")}</span>`;
        }
    } else if (rec.visibility === "public") {
        visibilityPill = `<span class="pill-visibility pill-public">🌐 Publique</span>`;
    } else {
        visibilityPill = `<span class="pill-visibility pill-shared">🤝 Partagée par ${rec.author_name}</span>`;
    }

    // Seasonality badge
    const seasonBadge = rec.seasonality_score === 100
        ? `<span class="badge badge-success">🌱 100% de saison</span>`
        : `<span class="badge badge-warning">🌱 ${rec.seasonality_score}% de saison</span>`;

    const totalTime = (rec.prep_time_minutes || 0) + (rec.cook_time_minutes || 0);

    // Ingredients list
    const ingredientsHtml = rec.ingredients.map((ing) => {
        let statusIcon = "•";
        let statusClass = "status-available";

        if (ing.status === "available") {
            statusIcon = "✓";
            statusClass = "status-available";
        } else if (ing.status === "missing") {
            statusIcon = "✕";
            statusClass = "status-missing";
        }

        let impLabel = "Optionnel";
        let impClass = "";
        if (ing.importance === 3) {
            impLabel = "Indispensable";
            impClass = "importance-essential";
        } else if (ing.importance === 2) {
            impLabel = "Majeur";
        }

        return `
            <div>
                <div class="ingredient-row">
                    <div class="ingredient-name-col">
                        <span class="status-icon ${statusClass}">${statusIcon}</span>
                        <span class="${ing.status === 'missing' ? 'text-muted' : ''}">${ing.name}</span>
                        <span class="importance-badge ${impClass}">${impLabel}</span>
                    </div>
                    <div>
                        <strong>${ing.quantity} ${ing.unit}</strong>
                    </div>
                </div>
            </div>
        `;
    }).join("");

    // Sharing actions row
    let actionsRow = `
        <div class="recipe-actions-row">
            <button type="button" class="btn-secondary btn-sm btn-copy-link" data-token="${rec.share_token}">
                🔗 Copier le lien de partage
            </button>
    `;

    if (rec.is_own) {
        const nextVisibility = rec.visibility === "public" ? "private" : "public";
        const toggleLabel = rec.visibility === "public" ? "Rendre privée 🔒" : "Rendre publique 🌐";

        // Exclude already shared accounts
        const shareableAccounts = state.allAccounts.filter(a =>
            a.id !== state.activeAccountId &&
            !(rec.shared_with_ids && rec.shared_with_ids.includes(a.id)) &&
            !(rec.shared_with && rec.shared_with.includes(a.display_name))
        );

        let shareSelectHtml = "";
        if (shareableAccounts.length > 0) {
            shareSelectHtml = `
                <select class="account-dropdown select-share-account" data-id="${rec.recipe_id}">
                    <option value="">Partager avec...</option>
                    ${shareableAccounts.map(a => `<option value="${a.id}">Partager avec ${a.display_name}</option>`).join("")}
                </select>
            `;
        } else {
            shareSelectHtml = `
                <select class="account-dropdown select-share-account" data-id="${rec.recipe_id}" disabled title="Déjà partagée avec tous vos proches">
                    <option value="">✓ Déjà partagée avec tous vos proches</option>
                </select>
            `;
        }

        actionsRow += `
            <div class="sharing-buttons-group">
                <button type="button" class="btn-secondary btn-sm btn-edit-recipe" data-id="${rec.recipe_id}">
                    ✏️ Modifier
                </button>
                <button type="button" class="btn-secondary btn-sm btn-toggle-vis" data-id="${rec.recipe_id}" data-next="${nextVisibility}">
                    ${toggleLabel}
                </button>
                ${shareSelectHtml}
            </div>
        `;
    }

    actionsRow += `</div>`;

    const detailFreezablePillHtml = rec.is_freezable
        ? `<span class="pill-freezable">❄️ Congélable</span>`
        : "";
    const detailRightHeaderHtml = (detailFreezablePillHtml || scorePillHtml)
        ? `<div class="recipe-card-header-right">${detailFreezablePillHtml}${scorePillHtml}</div>`
        : "";

    container.innerHTML = `
        ${vetoHtml}
        <div class="recipe-detail-header">
            <div>
                <div class="recipe-title-row">
                    <h2 class="recipe-detail-title">${rec.title}</h2>
                    ${alternativePill}
                    ${visibilityPill}
                </div>
                <div class="recipe-detail-meta">
                    <span>⏱️ Prépa : ${rec.prep_time_minutes} min</span>
                    <span>🔥 Cuisson : ${rec.cook_time_minutes} min</span>
                    <span>⏳ Total : ${totalTime} min</span>
                    <span>🍽️ Portions : ${rec.servings} pers.</span>
                    <span>👨‍🍳 Proposé par : <strong>${rec.author_name || "Communauté"}</strong></span>
                    ${seasonBadge}
                </div>
            </div>
            ${detailRightHeaderHtml}
        </div>

        <div class="recipe-detail-grid">
            <div>
                <h3 class="detail-section-title">Ingrédients (${rec.servings} pers.)</h3>
                <div class="recipe-detail-ingredients-box">
                    <div class="recipe-ingredients-list">
                        ${ingredientsHtml}
                    </div>
                </div>
            </div>
            <div>
                <h3 class="detail-section-title">Étapes de préparation</h3>
                <div class="recipe-detail-instructions-box">
                    ${formatInstructionsHtml(rec.instructions)}
                </div>
            </div>
        </div>

        ${actionsRow}
    `;

    attachCardActionListeners("recipe-detail-container");
}

/**
 * Show a quick toast notification on screen.
 */
function showToast(message) {
    const toast = document.getElementById("toast");
    if (!toast) return;

    toast.textContent = message;
    toast.style.display = "block";
    setTimeout(() => {
        toast.style.display = "none";
    }, 3000);
}

/**
 * Render the 12-month boxes calendar grid with ingredients in season for each month.
 */
function renderSeasonCalendar() {
    const gridContainer = document.getElementById("calendar-months-grid");
    const statsCount = document.getElementById("calendar-stats-count");
    const currentInfo = document.getElementById("calendar-current-info");
    if (!gridContainer) return;

    const currentMonth = new Date().getMonth() + 1; // 1 to 12

    const monthDefinitions = [
        { num: 1, name: "Janvier", emoji: "❄️", season: "winter", seasonClass: "season-winter" },
        { num: 2, name: "Février", emoji: "❄️", season: "winter", seasonClass: "season-winter" },
        { num: 3, name: "Mars", emoji: "🌸", season: "spring", seasonClass: "season-spring" },
        { num: 4, name: "Avril", emoji: "🌸", season: "spring", seasonClass: "season-spring" },
        { num: 5, name: "Mai", emoji: "🌸", season: "spring", seasonClass: "season-spring" },
        { num: 6, name: "Juin", emoji: "☀️", season: "summer", seasonClass: "season-summer" },
        { num: 7, name: "Juillet", emoji: "☀️", season: "summer", seasonClass: "season-summer" },
        { num: 8, name: "Août", emoji: "☀️", season: "summer", seasonClass: "season-summer" },
        { num: 9, name: "Septembre", emoji: "🍁", season: "autumn", seasonClass: "season-autumn" },
        { num: 10, name: "Octobre", emoji: "🍁", season: "autumn", seasonClass: "season-autumn" },
        { num: 11, name: "Novembre", emoji: "🍁", season: "autumn", seasonClass: "season-autumn" },
        { num: 12, name: "Décembre", emoji: "❄️", season: "winter", seasonClass: "season-winter" },
    ];

    const curMonthDef = monthDefinitions.find((m) => m.num === currentMonth);
    if (currentInfo && curMonthDef) {
        currentInfo.innerHTML = `Mois actuel : <strong>${curMonthDef.name} ${curMonthDef.emoji}</strong>`;
    }

    const categoryIcons = {
        "légume": "🥦",
        "champignon": "🍄",
        "fruit": "🍎",
        "féculent": "🍝",
        "légumineuse": "🫘",
        "protéine": "🥚",
        "viande": "🥩",
        "poisson": "🐟",
        "produit laitier": "🥛",
        "fromage": "🧀",
        "matière grasse": "🧈",
        "herbe/épice": "🌿",
        "condiment": "🧂",
        "produit sucré": "🍯",
        "produit végétal": "🌱",
        "autre": "📦"
    };

    // Filter parameters
    const searchVal = (state.seasonCalSearchQuery || "").toLowerCase().trim();
    const catVal = state.seasonCalFilterCategory || "all";
    const seasonVal = state.seasonCalFilterSeason || "all";
    const includeYearRound = state.seasonCalIncludeYearRound !== false;

    // Filter which month cards to display
    let visibleMonths = monthDefinitions;
    const monthVal = state.seasonCalFilterMonth || "all";
    if (monthVal !== "all") {
        const targetNum = parseInt(monthVal, 10);
        visibleMonths = monthDefinitions.filter((m) => m.num === targetNum);
    }

    // Active filter badge display (shows active filters in dark green)
    const activeFilterBadge = document.getElementById("calendar-active-filter-badge");
    if (activeFilterBadge) {
        const activeLabels = [];
        if (catVal !== "all") {
            const catIcon = categoryIcons[catVal] || "📦";
            activeLabels.push(`${catIcon} ${catVal.charAt(0).toUpperCase() + catVal.slice(1)}`);
        }
        if (monthVal !== "all") {
            const mDef = monthDefinitions.find(m => m.num === parseInt(monthVal, 10));
            if (mDef) activeLabels.push(`Mois : ${mDef.name} ${mDef.emoji}`);
        }
        if (searchVal) {
            activeLabels.push(`« ${searchVal} »`);
        }

        if (activeLabels.length > 0) {
            activeFilterBadge.style.display = "inline-flex";
            activeFilterBadge.innerHTML = `<span>Filtre sélectionné :</span> <strong>${activeLabels.join(" • ")}</strong>`;
        } else {
            activeFilterBadge.style.display = "none";
        }
    }

    // Filter active pool of ingredients based on search, category and year-round toggle
    const eligibleIngredients = state.allIngredients.filter((ing) => {
        // Search text
        if (searchVal && !ing.name.toLowerCase().includes(searchVal)) {
            return false;
        }

        // Category filter
        if (catVal !== "all" && ing.category.toLowerCase() !== catVal) {
            return false;
        }

        // Year-round toggle: if false, exclude ingredients available 12/12 months
        if (!includeYearRound && (ing.available_months || []).length === 12) {
            return false;
        }

        return true;
    });

    if (statsCount) {
        const countInCurrentMonth = eligibleIngredients.filter((ing) =>
            (ing.available_months || []).includes(currentMonth)
        ).length;

        statsCount.innerHTML = `Affichage de <strong>${visibleMonths.length} mois</strong> • ` +
            `<strong>${eligibleIngredients.length}</strong> ingrédient(s) filtré(s) ` +
            `(dont <strong>${countInCurrentMonth}</strong> de saison en ${curMonthDef ? curMonthDef.name : ""}).`;
    }

    gridContainer.innerHTML = visibleMonths.map((m) => {
        const isCurrentMonth = m.num === currentMonth;

        // In this month's box: ONLY ingredients that are in season in month m.num!
        const matchingIngredients = eligibleIngredients.filter((ing) => {
            const months = ing.available_months || [];
            return months.includes(m.num);
        });

        // Sort: strictly seasonal produce first, then year-round items, then alphabetical
        matchingIngredients.sort((a, b) => {
            const aYearRound = (a.available_months || []).length === 12 ? 1 : 0;
            const bYearRound = (b.available_months || []).length === 12 ? 1 : 0;
            if (aYearRound !== bYearRound) return aYearRound - bYearRound;
            return a.name.localeCompare(b.name);
        });

        let chipsHtml = "";
        if (matchingIngredients.length === 0) {
            chipsHtml = `<div class="month-empty-state">Aucun ingrédient correspondant en ${m.name}.</div>`;
        } else {
            chipsHtml = matchingIngredients.map((ing) => {
                const icon = categoryIcons[ing.category.toLowerCase()] || "📦";
                const isYearRound = (ing.available_months || []).length === 12;
                const chipClass = ing.needs_season_review
                    ? "chip-review-needed"
                    : (isYearRound ? "chip-year-round" : "chip-seasonal");
                const reviewMark = ing.needs_season_review ? "❓ " : "";
                const titleTooltip = `${ing.name} (${ing.category}) - ${isYearRound ? "Disponible toute l'année" : "En pleine saison"}`;

                return `
                    <span class="month-ing-chip ${chipClass}" title="${titleTooltip}">
                        <span>${icon}</span>
                        <span>${reviewMark}${ing.name}</span>
                    </span>
                `;
            }).join("");
        }

        return `
            <div class="month-card ${isCurrentMonth ? 'current-month-card' : ''}" data-month="${m.num}">
                <div class="month-card-header ${m.seasonClass}">
                    <div class="month-title-row">
                        <h3 class="month-name">${m.emoji} ${m.name}</h3>
                        ${isCurrentMonth ? '<span class="badge-cur-month">Mois en cours 🌱</span>' : ''}
                    </div>
                </div>
                <div class="month-ingredients-list">
                    ${chipsHtml}
                </div>
            </div>
        `;
    }).join("");
}

function formatMonthsRange(months) {
    if (!months || months.length === 0) return "Non renseigné";
    if (months.length === 12) return "Toute l'année";
    const shortNames = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"];
    const sorted = [...months].sort((a, b) => a - b);

    // Check if contiguous block
    let isContiguous = true;
    for (let i = 0; i < sorted.length - 1; i++) {
        if (sorted[i + 1] !== sorted[i] + 1) {
            isContiguous = false;
            break;
        }
    }
    if (isContiguous) {
        return `${shortNames[sorted[0]]} à ${shortNames[sorted[sorted.length - 1]]}`;
    }
    return sorted.map((m) => shortNames[m]).join(", ");
}
