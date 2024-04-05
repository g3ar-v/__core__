<script lang="ts">
  import { onMount, createEventDispatcher } from "svelte";
  import { extractObjectsbyName } from "$lib/utils";

  const dispatch = createEventDispatcher();

  let tts = "";
  let speakers: any = [];
  

  export let saveSettings: Function;
  
  onMount(async () => {
    let settings = JSON.parse(localStorage.getItem("settings") ?? "{}");
    tts = settings.audio.tts.module ?? "";
    
    speakers =
      extractObjectsbyName(settings.audio.tts, settings.audio.tts.module_options) ?? {};
  });
</script>

<form
  class="flex flex-col h-full justify-between space-y-3 text-sm"
  on:submit|preventDefault={() => {
    saveSettings(
      {
        audio: {
          tts: { module: tts },
          sounds: {
            start_listening:
              tts === "elevenlabs"
                ? "elevenlabs_takt"
                : "openai"
                ? "openai_echo"
                : "mimic3"
                ? "mimic3_apl"
                : undefined,
          },
      }
      },
      true
    );
    dispatch("save");
  }}
>
  <div class="flex flex-col space-y-3 text-sm mb-10">
    <div>
      
      <!-- <div class="flex w-full"> -->
      <!--   <div class="flex-1 mr-2"> -->
      <!--     <input -->
      <!--       class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none" -->
      <!--       placeholder="Enter model tag (e.g. mistral:7b)" -->
      <!--       bind:value={modelTag} -->
      <!--     /> -->
      <!--   </div> -->
      <!--   <button -->
      <!--     class="px-3 text-gray-100 bg-emerald-600 hover:bg-emerald-700 rounded transition" -->
      <!--     on:click={() => { -->
      <!--       pullModelHandler(); -->
      <!--     }} -->
      <!--   > -->
      <!--     <svg -->
      <!--       xmlns="http://www.w3.org/2000/svg" -->
      <!--       viewBox="0 0 20 20" -->
      <!--       fill="currentColor" -->
      <!--       class="w-4 h-4" -->
      <!--     > -->
      <!--       <path -->
      <!--         d="M10.75 2.75a.75.75 0 00-1.5 0v8.614L6.295 8.235a.75.75 0 10-1.09 1.03l4.25 4.5a.75.75 0 001.09 0l4.25-4.5a.75.75 0 00-1.09-1.03l-2.955 3.129V2.75z" -->
      <!--       /> -->
      <!--       <path -->
      <!--         d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z" -->
      <!--       /> -->
      <!--     </svg> -->
      <!--   </button> -->
      <!-- </div> -->

      <!-- <div class="mt-2 text-xs text-gray-400 dark:text-gray-500"> -->
      <!--   To access the available model names for downloading, <a -->
      <!--     class=" text-gray-500 dark:text-gray-300 font-medium" -->
      <!--     href="https://ollama.ai/library" -->
      <!--     target="_blank">click here.</a -->
      <!--   > -->
      <!-- </div> -->

      <!-- {#if pullProgress !== null} -->
      <!--   <div class="mt-2"> -->
      <!--     <div class=" mb-2 text-xs">Pull Progress</div> -->
      <!--     <div class="w-full rounded-full dark:bg-gray-800"> -->
      <!--       <div -->
      <!--         class="dark:bg-gray-600 text-xs font-medium text-blue-100 text-center p-0.5 leading-none rounded-full" -->
      <!--         style="width: {Math.max(15, pullProgress ?? 0)}%" -->
      <!--       > -->
      <!--         {pullProgress ?? 0}% -->
      <!--       </div> -->
      <!--     </div> -->
      <!--     <div -->
      <!--       class="mt-1 text-xs dark:text-gray-500" -->
      <!--       style="font-size: 0.5rem;" -->
      <!--     > -->
      <!--       {digest} -->
      <!--     </div> -->
      <!--   </div> -->
      <!-- {/if} -->
    </div>
    <!-- <hr class=" dark:border-gray-700" /> -->

    <div>
      <div class=" mb-2.5 text-sm font-medium">system speech module</div>
      <div class="flex w-full">
        <div class="flex-1 mr-2">
          <div>
            <div class="flex w-full">
              <div class="flex-1">
                <select
                  class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none"
                  bind:value={tts}
                  placeholder="Select tts module"
                >
                  {#each Object.keys(speakers) as voice}
                    <option
                      value={voice}
                      class="bg-gray-100 dark:bg-gray-700"
                      selected={voice === tts}>{voice}</option
                    >
                  {/each}
                </select>
              </div>
            </div>
          </div>
          <!-- <input -->

          <!--   class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none" -->
          <!--   placeholder="Enter module (e.g. openai, mimic) " -->
          <!--   bind:value={tts} -->
          <!-- /> -->
        </div>
      </div>
    </div>

    <hr class=" dark:border-gray-700" />
  </div>

  <div class="flex justify-end pt-3 text-sm font-medium">
    <button
      class=" px-4 py-2 bg-green-500 hover:bg-green-700 text-gray-950 transition rounded"
      type="submit"
    >
      Save
    </button>
  </div>
</form>
