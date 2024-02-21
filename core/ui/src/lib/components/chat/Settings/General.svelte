<script lang="ts">
  import { OLLAMA_API_BASE_URL } from "$lib/constants";
  import { onMount, createEventDispatcher } from "svelte";
  import { settings } from "$lib/stores";

  const dispatch = createEventDispatcher();
  let API_BASE_URL = OLLAMA_API_BASE_URL;
  let theme = "dark";
  let system = "";
  export let saveSettings: Function;

  const toggleTheme = async () => {
    API_BASE_URL = settings.API_BASE_URL ?? OLLAMA_API_BASE_URL;
    if (theme === "dark") {
      theme = "light";
    } else {
      theme = "dark";
    }

    localStorage.theme = theme;

    document.documentElement.classList.remove(
      theme === "dark" ? "light" : "dark"
    );
    document.documentElement.classList.add(theme);
  };

  onMount(() => {
    let settings = JSON.parse(localStorage.getItem("settings") ?? "{}");
    API_BASE_URL = settings.API_BASE_URL ?? OLLAMA_API_BASE_URL;
    theme = localStorage.theme ?? "dark";
    system = settings.system ?? "";
  });
</script>

<div class="flex flex-col space-y-3">
  <div>
    <div class=" py-1 flex w-full justify-between">
      <div class=" self-center text-sm font-medium">Theme</div>

      <button
        class="p-1 px-3 text-xs flex rounded transition"
        on:click={() => {
          toggleTheme();
        }}
      >
        {#if theme === "dark"}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            class="w-4 h-4"
          >
            <path
              fill-rule="evenodd"
              d="M7.455 2.004a.75.75 0 01.26.77 7 7 0 009.958 7.967.75.75 0 011.067.853A8.5 8.5 0 116.647 1.921a.75.75 0 01.808.083z"
              clip-rule="evenodd"
            />
          </svg>

          <span class="ml-2 self-center"> Dark </span>
        {:else}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            class="w-4 h-4 self-center"
          >
            <path
              d="M10 2a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2zM10 15a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 15zM10 7a3 3 0 100 6 3 3 0 000-6zM15.657 5.404a.75.75 0 10-1.06-1.06l-1.061 1.06a.75.75 0 001.06 1.06l1.06-1.06zM6.464 14.596a.75.75 0 10-1.06-1.06l-1.06 1.06a.75.75 0 001.06 1.06l1.06-1.06zM18 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5A.75.75 0 0118 10zM5 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5A.75.75 0 015 10zM14.596 15.657a.75.75 0 001.06-1.06l-1.06-1.061a.75.75 0 10-1.06 1.06l1.06 1.06zM5.404 6.464a.75.75 0 001.06-1.06l-1.06-1.06a.75.75 0 10-1.061 1.06l1.06 1.06z"
            />
          </svg>
          <span class="ml-2 self-center"> Light </span>
        {/if}
      </button>
    </div>
  </div>

  <hr class=" dark:border-gray-700" />
  <div>
    <div class=" mb-2.5 text-sm font-medium">UI BACKEND URL</div>
    <div class="flex w-full">
      <div class="flex-1 mr-2">
        <input
          class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none"
          placeholder="Enter URL (e.g. http://localhost:11434)"
          bind:value={API_BASE_URL}
        />
      </div>
    </div>
  </div>

  <hr class=" dark:border-gray-700" />

  <div class="flex justify-end pt-3 text-sm font-medium">
    <button
      class=" px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-gray-100 transition rounded"
      on:click={() => {
        saveSettings({
          API_BASE_URL:
            API_BASE_URL === "" ? OLLAMA_API_BASE_URL : API_BASE_URL,
          system: system !== "" ? system : undefined,
        });
        dispatch("save");
      }}
    >
      Save
    </button>
  </div>
</div>
