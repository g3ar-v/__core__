<script lang="ts">
  import Modal from "../common/Modal.svelte";

  import { WEB_UI_VERSION, OLLAMA_API_BASE_URL } from "$lib/constants";
  import toast from "svelte-french-toast";
  import { onMount } from "svelte";
  import { config, settings, user } from "$lib/stores";
  import { splitStream, fetchAndSetCoreSettings } from "$lib/utils";
  import Advanced from "./Settings/Advanced.svelte";
  import Voice from "./Settings/Voice.svelte";
  import Audio from "./Settings/Audio.svelte";
  import General from "./Settings/General.svelte";

  export let show = false;

  /**
   * Saves the updated settings both locally and optionally to the backend.
   *
   * This function merges the updated settings with the current settings and saves them
   * to the local storage. If specified, the updated settings are also sent to the backend.
   *
   * @param {Object} updated - The updated settings to be saved.
   * @param {Boolean} [sendToBackend=false] - Flag indicating whether to send the updated settings to the backend.
   */
  const saveSettings = async (
    updated: Object,
    sendToBackend: Boolean = false
  ) => {
    // settings.set({ ...$settings, ...updated });
    // Save the updated settings to local storage
    // localStorage.setItem("settings", JSON.stringify($settings));
    // If sendToBackend flag is true, send the updated settings to the backend
    if (sendToBackend) {
      await setBackendSettings(updated);
      await fetchAndSetCoreSettings($settings);
    } else {
      await fetchAndSetCoreSettings($settings);
    }
  };

  const setBackendSettings = async (updated: Object) => {
    try {
      await fetch(
        `${$settings?.API_BASE_URL ?? OLLAMA_API_BASE_URL}v1/system/config/set`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(updated),
        }
      );
    } catch (error) {
      // Handle error
      // toast.error("Error fetching core settings:" + error);
      return null; // or throw error
    }
  };
  let selectedTab = "general";

  // Advanced
  let requestFormat = "";
  let options = {
    // Advanced
    seed: 0,
    temperature: "",
    repeat_penalty: "",
    repeat_last_n: "",
    mirostat: "",
    mirostat_eta: "",
    mirostat_tau: "",
    top_k: "",
    top_p: "",
    stop: "",
    tfs_z: "",
    num_ctx: "",
  };

  // Output Audio

  // Voice

  let titleAutoGenerate = true;
  let speechAutoSend = false;
  let gravatarEmail = "";
  let OPENAI_API_KEY = "";

  // Auth
  let authEnabled = false;
  let authType = "Basic";
  let authContent = "";

  const toggleRequestFormat = async () => {
    if (requestFormat === "") {
      requestFormat = "json";
    } else {
      requestFormat = "";
    }

    saveSettings({
      requestFormat: requestFormat !== "" ? requestFormat : undefined,
    });
  };

  const toggleSpeechAutoSend = async () => {
    speechAutoSend = !speechAutoSend;
    saveSettings({ speechAutoSend: speechAutoSend });
  };

  const toggleTitleAutoGenerate = async () => {
    titleAutoGenerate = !titleAutoGenerate;
    saveSettings({ titleAutoGenerate: titleAutoGenerate });
  };

  const toggleAuthHeader = async () => {
    authEnabled = !authEnabled;
  };

  onMount(() => {
    let settings = JSON.parse(localStorage.getItem("settings") ?? "{}");

    // console.log("settings conf: " + JSON.stringify(backend_settings, null, 4));

    requestFormat = settings.requestFormat ?? "";

    options.seed = settings.seed ?? 0;
    options.temperature = settings.temperature ?? "";
    options.repeat_penalty = settings.repeat_penalty ?? "";
    options.top_k = settings.top_k ?? "";
    options.top_p = settings.top_p ?? "";
    options.num_ctx = settings.num_ctx ?? "";
    options = { ...options, ...settings.options };

    titleAutoGenerate = settings.titleAutoGenerate ?? true;
    speechAutoSend = settings.speechAutoSend ?? false;
    gravatarEmail = settings.gravatarEmail ?? "";
    OPENAI_API_KEY = settings.OPENAI_API_KEY ?? "";

    authEnabled = settings.authHeader !== undefined ? true : false;
    if (authEnabled) {
      authType = settings.authHeader.split(" ")[0];
      authContent = settings.authHeader.split(" ")[1];
    }
  });
</script>

<Modal bind:show>
  <div>
    <div class=" flex justify-between dark:text-gray-300 px-5 py-4">
      <div class=" text-lg font-medium self-center">Settings</div>
      <button
        class="self-center"
        on:click={() => {
          show = false;
        }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          class="w-5 h-5"
        >
          <path
            d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
          />
        </svg>
      </button>
    </div>
    <hr class=" dark:border-gray-800" />

    <div class="flex flex-col md:flex-row w-full p-4 md:space-x-4">
      <div
        class="tabs flex flex-row overflow-x-auto space-x-1 md:space-x-0 md:space-y-1 md:flex-col flex-1 md:flex-none md:w-40 dark:text-gray-200 text-xs text-left mb-3 md:mb-0"
      >
        <button
          class="px-2.5 py-2.5 min-w-fit rounded-lg flex-1 md:flex-none flex text-right transition {selectedTab ===
          'general'
            ? 'bg-gray-200 dark:bg-gray-700'
            : ' hover:bg-gray-300 dark:hover:bg-gray-800'}"
          on:click={() => {
            selectedTab = "general";
          }}
        >
          <div class=" self-center mr-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              class="w-4 h-4"
            >
              <path
                fill-rule="evenodd"
                d="M8.34 1.804A1 1 0 019.32 1h1.36a1 1 0 01.98.804l.295 1.473c.497.144.971.342 1.416.587l1.25-.834a1 1 0 011.262.125l.962.962a1 1 0 01.125 1.262l-.834 1.25c.245.445.443.919.587 1.416l1.473.294a1 1 0 01.804.98v1.361a1 1 0 01-.804.98l-1.473.295a6.95 6.95 0 01-.587 1.416l.834 1.25a1 1 0 01-.125 1.262l-.962.962a1 1 0 01-1.262.125l-1.25-.834a6.953 6.953 0 01-1.416.587l-.294 1.473a1 1 0 01-.98.804H9.32a1 1 0 01-.98-.804l-.295-1.473a6.957 6.957 0 01-1.416-.587l-1.25.834a1 1 0 01-1.262-.125l-.962-.962a1 1 0 01-.125-1.262l.834-1.25a6.957 6.957 0 01-.587-1.416l-1.473-.294A1 1 0 011 10.68V9.32a1 1 0 01.804-.98l1.473-.295c.144-.497.342-.971.587-1.416l-.834-1.25a1 1 0 01.125-1.262l.962-.962A1 1 0 015.38 3.03l1.25.834a6.957 6.957 0 011.416-.587l.294-1.473zM13 10a3 3 0 11-6 0 3 3 0 016 0z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class=" self-center">General</div>
        </button>

        <button
          class="px-2.5 py-2.5 min-w-fit rounded-lg flex-1 md:flex-none flex text-right transition {selectedTab ===
          'voice'
            ? 'bg-gray-200 dark:bg-gray-700'
            : ' hover:bg-gray-300 dark:hover:bg-gray-800'}"
          on:click={() => {
            selectedTab = "voice";
          }}
        >
          <div class=" self-center mr-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              class="w-4 h-4"
            >
              <path
                d="M12 4.467c0-.405.262-.75.559-1.027.276-.257.441-.584.441-.94 0-.828-.895-1.5-2-1.5s-2 .672-2 1.5c0 .362.171.694.456.953.29.265.544.6.544.994a.968.968 0 01-1.024.974 39.655 39.655 0 01-3.014-.306.75.75 0 00-.847.847c.14.993.242 1.999.306 3.014A.968.968 0 014.447 10c-.393 0-.729-.253-.994-.544C3.194 9.17 2.862 9 2.5 9 1.672 9 1 9.895 1 11s.672 2 1.5 2c.356 0 .683-.165.94-.441.276-.297.622-.559 1.027-.559a.997.997 0 011.004 1.03 39.747 39.747 0 01-.319 3.734.75.75 0 00.64.842c1.05.146 2.111.252 3.184.318A.97.97 0 0010 16.948c0-.394-.254-.73-.545-.995C9.171 15.693 9 15.362 9 15c0-.828.895-1.5 2-1.5s2 .672 2 1.5c0 .356-.165.683-.441.94-.297.276-.559.622-.559 1.027a.998.998 0 001.03 1.005c1.337-.05 2.659-.162 3.961-.337a.75.75 0 00.644-.644c.175-1.302.288-2.624.337-3.961A.998.998 0 0016.967 12c-.405 0-.75.262-1.027.559-.257.276-.584.441-.94.441-.828 0-1.5-.895-1.5-2s.672-2 1.5-2c.362 0 .694.17.953.455.265.291.601.545.995.545a.97.97 0 00.976-1.024 41.159 41.159 0 00-.318-3.184.75.75 0 00-.842-.64c-1.228.164-2.473.271-3.734.319A.997.997 0 0112 4.467z"
              />
            </svg>
          </div>
          <div class=" self-center">Voice</div>
        </button>
        <button
          class="px-2.5 py-2.5 min-w-fit rounded-lg flex-1 md:flex-none flex text-right transition {selectedTab ===
          'audio'
            ? 'bg-gray-200 dark:bg-gray-700'
            : ' hover:bg-gray-300 dark:hover:bg-gray-800'}"
          on:click={() => {
            selectedTab = "audio";
          }}
        >
          <div class=" self-center mr-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              class="w-4 h-4"
            >
              <path
                fill-rule="evenodd"
                d="M10 1c3.866 0 7 1.79 7 4s-3.134 4-7 4-7-1.79-7-4 3.134-4 7-4zm5.694 8.13c.464-.264.91-.583 1.306-.952V10c0 2.21-3.134 4-7 4s-7-1.79-7-4V8.178c.396.37.842.688 1.306.953C5.838 10.006 7.854 10.5 10 10.5s4.162-.494 5.694-1.37zM3 13.179V15c0 2.21 3.134 4 7 4s7-1.79 7-4v-1.822c-.396.37-.842.688-1.306.953-1.532.875-3.548 1.369-5.694 1.369s-4.162-.494-5.694-1.37A7.009 7.009 0 013 13.179z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class=" self-center">Audio</div>
        </button>

        <!-- {#if !$config || ($config && !$config.auth)} -->
        <!--   <button -->
        <!--     class="px-2.5 py-2.5 min-w-fit rounded-lg flex-1 md:flex-none flex text-right transition {selectedTab === -->
        <!--     'auth' -->
        <!--       ? 'bg-gray-200 dark:bg-gray-700' -->
        <!--       : ' hover:bg-gray-300 dark:hover:bg-gray-800'}" -->
        <!--     on:click={() => { -->
        <!--       selectedTab = "auth"; -->
        <!--     }} -->
        <!--   > -->
        <!--     <div class=" self-center mr-2"> -->
        <!--       <svg -->
        <!--         xmlns="http://www.w3.org/2000/svg" -->
        <!--         viewBox="0 0 24 24" -->
        <!--         fill="currentColor" -->
        <!--         class="w-4 h-4" -->
        <!--       > -->
        <!--         <path -->
        <!--           fill-rule="evenodd" -->
        <!--           d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516l-.143.001c-2.996 0-5.717-1.17-7.734-3.08zm3.094 8.016a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z" -->
        <!--           clip-rule="evenodd" -->
        <!--         /> -->
        <!--       </svg> -->
        <!--     </div> -->
        <!--     <div class=" self-center">Authentication</div> -->
        <!--   </button> -->
        <!-- {/if} -->
        <!-- <button -->
        <!--   class="px-2.5 py-2.5 min-w-fit rounded-lg flex-1 md:flex-none flex text-right transition {selectedTab === -->
        <!--   'advanced' -->
        <!--     ? 'bg-gray-200 dark:bg-gray-700' -->
        <!--     : ' hover:bg-gray-300 dark:hover:bg-gray-800'}" -->
        <!--   on:click={() => { -->
        <!--     selectedTab = "advanced"; -->
        <!--   }} -->
        <!-- > -->
        <!--   <div class=" self-center mr-2"> -->
        <!--     <svg -->
        <!--       xmlns="http://www.w3.org/2000/svg" -->
        <!--       viewBox="0 0 20 20" -->
        <!--       fill="currentColor" -->
        <!--       class="w-4 h-4" -->
        <!--     > -->
        <!--       <path -->
        <!--         d="M17 2.75a.75.75 0 00-1.5 0v5.5a.75.75 0 001.5 0v-5.5zM17 15.75a.75.75 0 00-1.5 0v1.5a.75.75 0 001.5 0v-1.5zM3.75 15a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5a.75.75 0 01.75-.75zM4.5 2.75a.75.75 0 00-1.5 0v5.5a.75.75 0 001.5 0v-5.5zM10 11a.75.75 0 01.75.75v5.5a.75.75 0 01-1.5 0v-5.5A.75.75 0 0110 11zM10.75 2.75a.75.75 0 00-1.5 0v1.5a.75.75 0 001.5 0v-1.5zM10 6a2 2 0 100 4 2 2 0 000-4zM3.75 10a2 2 0 100 4 2 2 0 000-4zM16.25 10a2 2 0 100 4 2 2 0 000-4z" -->
        <!--       /> -->
        <!--     </svg> -->
        <!--   </div> -->
        <!--   <div class=" self-center">Advanced</div> -->
        <!-- </button> -->
        <button
          class="px-2.5 py-2.5 min-w-fit rounded-lg flex-1 md:flex-none flex text-right transition {selectedTab ===
          'about'
            ? 'bg-gray-200 dark:bg-gray-700'
            : ' hover:bg-gray-300 dark:hover:bg-gray-800'}"
          on:click={() => {
            selectedTab = "about";
          }}
        >
          <div class=" self-center mr-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              class="w-4 h-4"
            >
              <path
                fill-rule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class=" self-center">About</div>
        </button>
      </div>
      <div class="flex-1 md:min-h-[340px]">
        {#if selectedTab === "general"}
          <General
            on:save={() => {
              show = false;
            }}
            {saveSettings}
          />
          <!-- {:else if selectedTab === "advanced"} -->
          <!--   <div class="flex flex-col h-full justify-between text-sm"> -->
          <!--     <div class=" space-y-3 pr-1.5 overflow-y-scroll max-h-72"> -->
          <!--       <div class=" text-sm font-medium">Parameters</div> -->
          <!---->
          <!--       <Advanced bind:options /> -->
          <!--       <hr class=" dark:border-gray-700" /> -->
          <!---->
          <!--       <div> -->
          <!--         <div class=" py-1 flex w-full justify-between"> -->
          <!--           <div class=" self-center text-sm font-medium"> -->
          <!--             Request Mode -->
          <!--           </div> -->
          <!---->
          <!--           <button -->
          <!--             class="p-1 px-3 text-xs flex rounded transition" -->
          <!--             on:click={() => { -->
          <!--               toggleRequestFormat(); -->
          <!--             }} -->
          <!--           > -->
          <!--             {#if requestFormat === ""} -->
          <!--               <span class="ml-2 self-center"> Default </span> -->
          <!--             {:else if requestFormat === "json"} -->
          <!--               <!-- <svg -->
          <!-- 				xmlns="http://www.w3.org/2000/svg" -->
          <!-- 				viewBox="0 0 20 20" -->
          <!-- 				fill="currentColor" -->
          <!-- 				class="w-4 h-4 self-center" -->
          <!-- 			> -->
          <!-- 				<path -->
          <!-- 					d="M10 2a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2zM10 15a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 15zM10 7a3 3 0 100 6 3 3 0 000-6zM15.657 5.404a.75.75 0 10-1.06-1.06l-1.061 1.06a.75.75 0 001.06 1.06l1.06-1.06zM6.464 14.596a.75.75 0 10-1.06-1.06l-1.06 1.06a.75.75 0 001.06 1.06l1.06-1.06zM18 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5A.75.75 0 0118 10zM5 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5A.75.75 0 015 10zM14.596 15.657a.75.75 0 001.06-1.06l-1.06-1.061a.75.75 0 10-1.06 1.06l1.06 1.06zM5.404 6.464a.75.75 0 001.06-1.06l-1.06-1.06a.75.75 0 10-1.061 1.06l1.06 1.06z" -->
          <!-- 				/> -->
          <!-- </svg>  -->
          <!--               <span class="ml-2 self-center"> JSON </span> -->
          <!--             {/if} -->
          <!--           </button> -->
          <!--         </div> -->
          <!--       </div> -->
          <!--     </div> -->
          <!---->
          <!--     <div class="flex justify-end pt-3 text-sm font-medium"> -->
          <!--       <button -->
          <!--         class=" px-4 py-2 bg-green-800 hover:bg-green-700 text-gray-100 transition rounded" -->
          <!--         on:click={() => { -->
          <!--           saveSettings({ -->
          <!--             options: { -->
          <!--               seed: -->
          <!--                 (options.seed !== 0 ? options.seed : undefined) ?? -->
          <!--                 undefined, -->
          <!--               stop: options.stop !== "" ? options.stop : undefined, -->
          <!--               temperature: -->
          <!--                 options.temperature !== "" -->
          <!--                   ? options.temperature -->
          <!--                   : undefined, -->
          <!--               repeat_penalty: -->
          <!--                 options.repeat_penalty !== "" -->
          <!--                   ? options.repeat_penalty -->
          <!--                   : undefined, -->
          <!--               repeat_last_n: -->
          <!--                 options.repeat_last_n !== "" -->
          <!--                   ? options.repeat_last_n -->
          <!--                   : undefined, -->
          <!--               mirostat: -->
          <!--                 options.mirostat !== "" ? options.mirostat : undefined, -->
          <!--               mirostat_eta: -->
          <!--                 options.mirostat_eta !== "" -->
          <!--                   ? options.mirostat_eta -->
          <!--                   : undefined, -->
          <!--               mirostat_tau: -->
          <!--                 options.mirostat_tau !== "" -->
          <!--                   ? options.mirostat_tau -->
          <!--                   : undefined, -->
          <!--               top_k: options.top_k !== "" ? options.top_k : undefined, -->
          <!--               top_p: options.top_p !== "" ? options.top_p : undefined, -->
          <!--               tfs_z: options.tfs_z !== "" ? options.tfs_z : undefined, -->
          <!--               num_ctx: -->
          <!--                 options.num_ctx !== "" ? options.num_ctx : undefined, -->
          <!--             }, -->
          <!--           }); -->
          <!--           show = false; -->
          <!--         }} -->
          <!--       > -->
          <!--         Save -->
          <!--       </button> -->
          <!--     </div> -->
          <!--   </div> -->
        {:else if selectedTab === "voice"}
          <Voice
            on:save={() => {
              show = false;
            }}
            {saveSettings}
          />
        {:else if selectedTab === "audio"}
          <Audio
            on:save={() => {
              show = false;
            }}
            {saveSettings}
          />
          <!-- {:else if selectedTab === "auth"} -->
          <!--   <form -->
          <!--     class="flex flex-col h-full justify-between space-y-3 text-sm" -->
          <!--     on:submit|preventDefault={() => { -->
          <!--       console.log("auth save"); -->
          <!--       saveSettings({ -->
          <!--         authHeader: authEnabled -->
          <!--           ? `${authType} ${authContent}` -->
          <!--           : undefined, -->
          <!--       }); -->
          <!--       show = false; -->
          <!--     }} -->
          <!--   > -->
          <!--     <div class=" space-y-3"> -->
          <!--       <div> -->
          <!--         <div class=" py-1 flex w-full justify-between"> -->
          <!--           <div class=" self-center text-sm font-medium"> -->
          <!--             Authorization Header -->
          <!--           </div> -->
          <!---->
          <!--           <button -->
          <!--             class="p-1 px-3 text-xs flex rounded transition" -->
          <!--             type="button" -->
          <!--             on:click={() => { -->
          <!--               toggleAuthHeader(); -->
          <!--             }} -->
          <!--           > -->
          <!--             {#if authEnabled === true} -->
          <!--               <svg -->
          <!--                 xmlns="http://www.w3.org/2000/svg" -->
          <!--                 viewBox="0 0 24 24" -->
          <!--                 fill="currentColor" -->
          <!--                 class="w-4 h-4" -->
          <!--               > -->
          <!--                 <path -->
          <!--                   fill-rule="evenodd" -->
          <!--                   d="M12 1.5a5.25 5.25 0 00-5.25 5.25v3a3 3 0 00-3 3v6.75a3 3 0 003 3h10.5a3 3 0 003-3v-6.75a3 3 0 00-3-3v-3c0-2.9-2.35-5.25-5.25-5.25zm3.75 8.25v-3a3.75 3.75 0 10-7.5 0v3h7.5z" -->
          <!--                   clip-rule="evenodd" -->
          <!--                 /> -->
          <!--               </svg> -->
          <!---->
          <!--               <span class="ml-2 self-center"> On </span> -->
          <!--             {:else} -->
          <!--               <svg -->
          <!--                 xmlns="http://www.w3.org/2000/svg" -->
          <!--                 viewBox="0 0 24 24" -->
          <!--                 fill="currentColor" -->
          <!--                 class="w-4 h-4" -->
          <!--               > -->
          <!--                 <path -->
          <!--                   d="M18 1.5c2.9 0 5.25 2.35 5.25 5.25v3.75a.75.75 0 01-1.5 0V6.75a3.75 3.75 0 10-7.5 0v3a3 3 0 013 3v6.75a3 3 0 01-3 3H3.75a3 3 0 01-3-3v-6.75a3 3 0 013-3h9v-3c0-2.9 2.35-5.25 5.25-5.25z" -->
          <!--                 /> -->
          <!--               </svg> -->
          <!---->
          <!--               <span class="ml-2 self-center">Off</span> -->
          <!--             {/if} -->
          <!--           </button> -->
          <!--         </div> -->
          <!--       </div> -->
          <!---->
          <!--       {#if authEnabled} -->
          <!--         <hr class=" dark:border-gray-700" /> -->
          <!---->
          <!--         <div class="mt-2"> -->
          <!--           <div class=" py-1 flex w-full space-x-2"> -->
          <!--             <button -->
          <!--               class=" py-1 font-semibold flex rounded transition" -->
          <!--               on:click={() => { -->
          <!--                 authType = authType === "Basic" ? "Bearer" : "Basic"; -->
          <!--               }} -->
          <!--               type="button" -->
          <!--             > -->
          <!--               {#if authType === "Basic"} -->
          <!--                 <span class="self-center mr-2">Basic</span> -->
          <!--               {:else if authType === "Bearer"} -->
          <!--                 <span class="self-center mr-2">Bearer</span> -->
          <!--               {/if} -->
          <!--             </button> -->
          <!---->
          <!--             <div class="flex-1"> -->
          <!--               <input -->
          <!--                 class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none" -->
          <!--                 placeholder="Enter Authorization Header Content" -->
          <!--                 bind:value={authContent} -->
          <!--               /> -->
          <!--             </div> -->
          <!--           </div> -->
          <!--           <div class="mt-2 text-xs text-gray-400 dark:text-gray-500"> -->
          <!--             Toggle between <span -->
          <!--               class=" text-gray-500 dark:text-gray-300 font-medium" -->
          <!--               >'Basic'</span -->
          <!--             > -->
          <!--             and -->
          <!--             <span class=" text-gray-500 dark:text-gray-300 font-medium" -->
          <!--               >'Bearer'</span -->
          <!--             > by clicking on the label next to the input. -->
          <!--           </div> -->
          <!--         </div> -->
          <!---->
          <!--         <hr class=" dark:border-gray-700" /> -->
          <!---->
          <!--         <div> -->
          <!--           <div class=" mb-2.5 text-sm font-medium"> -->
          <!--             Preview Authorization Header -->
          <!--           </div> -->
          <!--           <textarea -->
          <!--             value={JSON.stringify({ -->
          <!--               Authorization: `${authType} ${authContent}`, -->
          <!--             })} -->
          <!--             class="w-full rounded p-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none resize-none" -->
          <!--             rows="2" -->
          <!--             disabled -->
          <!--           /> -->
          <!--         </div> -->
          <!--       {/if} -->
          <!--       <div> -->
          <!--         <div class=" mb-2.5 text-sm font-medium"> -->
          <!--           Gravatar Email <span class=" text-gray-400 text-sm" -->
          <!--             >(optional)</span -->
          <!--           > -->
          <!--         </div> -->
          <!--         <div class="flex w-full"> -->
          <!--           <div class="flex-1"> -->
          <!--             <input -->
          <!--               class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none" -->
          <!--               placeholder="Enter Your Email" -->
          <!--               bind:value={gravatarEmail} -->
          <!--               autocomplete="off" -->
          <!--               type="email" -->
          <!--             /> -->
          <!--           </div> -->
          <!--         </div> -->
          <!--         <div class="mt-2 text-xs text-gray-400 dark:text-gray-500"> -->
          <!--           Changes user profile image to match your <a -->
          <!--             class=" text-gray-500 dark:text-gray-300 font-medium" -->
          <!--             href="https://gravatar.com/" -->
          <!--             target="_blank">Gravatar.</a -->
          <!--           > -->
          <!--         </div> -->
          <!--       </div> -->
          <!---->
          <!--       <hr class=" dark:border-gray-700" /> -->
          <!--       <div> -->
          <!--         <div class=" mb-2.5 text-sm font-medium"> -->
          <!--           OpenAI API Key <span class=" text-gray-400 text-sm" -->
          <!--             >(optional)</span -->
          <!--           > -->
          <!--         </div> -->
          <!--         <div class="flex w-full"> -->
          <!--           <div class="flex-1"> -->
          <!--             <input -->
          <!--               class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none" -->
          <!--               placeholder="Enter OpenAI API Key" -->
          <!--               bind:value={OPENAI_API_KEY} -->
          <!--               autocomplete="off" -->
          <!--             /> -->
          <!--           </div> -->
          <!--         </div> -->
          <!--         <div class="mt-2 text-xs text-gray-400 dark:text-gray-500"> -->
          <!--           Adds optional support for 'gpt-*' models available. -->
          <!--         </div> -->
          <!--       </div> -->
          <!--     </div> -->
          <!---->
          <!--     <div class="flex justify-end pt-3 text-sm font-medium"> -->
          <!--       <button -->
          <!--         class=" px-4 py-2 bg-green-800 hover:bg-green-700 text-gray-100 transition rounded" -->
          <!--         type="submit" -->
          <!--       > -->
          <!--         Save -->
          <!--       </button> -->
          <!--     </div> -->
          <!--   </form> -->
        {:else if selectedTab === "about"}
          <div
            class="flex flex-col h-full justify-between space-y-3 text-sm mb-6"
          >
            <div class=" space-y-3">
              <div>
                <div class=" mb-2.5 text-sm font-medium">
                  CORE Web UI Version
                </div>
                <div class="flex w-full">
                  <div class="flex-1 text-xs text-gray-700 dark:text-gray-200">
                    {$config && $config.version
                      ? $config.version
                      : WEB_UI_VERSION}
                  </div>
                </div>
              </div>

              <hr class=" dark:border-gray-700" />

              <div class="mt-2 text-xs text-gray-400 dark:text-gray-500">
                Created by <a
                  class=" text-gray-500 dark:text-gray-300 font-medium"
                  href="https://github.com/tjbck"
                  target="_blank">g3ar</a
                >
              </div>
            </div>
          </div>
        {/if}
      </div>
    </div>
  </div>
</Modal>

<style>
  input::-webkit-outer-spin-button,
  input::-webkit-inner-spin-button {
    /* display: none; <- Crashes Chrome on hover */
    -webkit-appearance: none;
    margin: 0; /* <-- Apparently some margin are still there even though it's hidden */
  }

  .tabs::-webkit-scrollbar {
    display: none; /* for Chrome, Safari and Opera */
  }

  .tabs {
    -ms-overflow-style: none; /* IE and Edge */
    scrollbar-width: none; /* Firefox */
  }

  input[type="number"] {
    -moz-appearance: textfield; /* Firefox */
  }
</style>
