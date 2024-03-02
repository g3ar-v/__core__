<script lang="ts">
  import { onMount, createEventDispatcher } from "svelte";

  const dispatch = createEventDispatcher();

  let stt = "";
  let sttModelType = "";
  let sttModelTypeOptions = "";
  let vadSilence = 0;
  let recordingTimeout = 0;

  export let saveSettings: Function;

  onMount(async () => {
    let settings = JSON.parse(localStorage.getItem("settings") ?? "{}");
    stt = settings.stt.module ?? "";
    sttModelType = settings.stt[stt]?.model ?? "";
    sttModelTypeOptions = settings.stt.model_type ?? [];
    vadSilence = settings.listener.VAD.silence_seconds ?? 0;
    recordingTimeout = settings.listener.recording_timeout ?? 0;
    // console.log(sttModelTypeOptions);
  });
</script>

<form
  class="flex flex-col h-full justify-between space-y-3 text-sm"
  on:submit|preventDefault={() => {
    saveSettings(
      {
        stt: {
          module: stt !== "" ? stt : undefined,
          whisper: { model: sttModelType },
        },
        listener: {
          VAD: {
            silence_seconds: vadSilence,
          },
          recording_timeout: recordingTimeout,
        },
      },
      true
    );
    dispatch("save");
  }}
>
  <div class="flex flex-col space-y-3 text-sm mb-10">
    <div class="space-y-3">
      <div>
        <div class=" py-0.5 flex w-full justify-between">
          <div class=" w-40 text-sm font-medium self-center">
            Recording Timeout
          </div>
          <div class=" flex-1 self-center">
            <input
              class="w-full rounded py-1.5 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none border border-gray-100 dark:border-gray-600"
              type="number"
              placeholder="Enter recording timeout secs"
              bind:value={recordingTimeout}
              autocomplete="off"
              min="0"
            />
          </div>
        </div>
      </div>
      <div>
        <div class=" py-0.5 flex w-full justify-between">
          <div class=" w-40 text-sm font-medium self-center">
            VAD Max Silence
          </div>
          <div class=" flex-1 self-center">
            <input
              class="w-full rounded py-1.5 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none border border-gray-100 dark:border-gray-600"
              type="number"
              placeholder="Enter max silence secs"
              bind:value={vadSilence}
              autocomplete="off"
              min="0"
              step="0.1"
            />
          </div>
        </div>
      </div>
      <hr class=" dark:border-gray-700" />

      <div class=" mb-2.5 text-sm font-medium">Speech-to-Text Module</div>
      <div class="flex w-full">
        <div class="flex-1">
          <input
            class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none"
            placeholder="enter stt module for spee recognition"
            bind:value={stt}
            autocomplete="off"
            type="text"
          />
        </div>
      </div>
    </div>

    <div>
      <div class=" mb-2.5 text-sm font-medium">Model Type</div>
      <div class="flex w-full">
        <div class="flex-1">
          <select
            class="w-full rounded py-2 px-4 text-sm dark:text-gray-300 dark:bg-gray-800 outline-none"
            bind:value={sttModelType}
            placeholder="Select tts module"
          >
            {#each sttModelTypeOptions as modelOptions}
              <option
                value={modelOptions}
                class="bg-gray-100 dark:bg-gray-700"
                selected={sttModelType === modelOptions}
              >
                {modelOptions}
              </option>
            {/each}
          </select>
        </div>
      </div>
    </div>
  </div>

  <div class="flex justify-end pt-3 text-sm font-medium">
    <button
      class=" px-4 py-2 bg-green-800 hover:bg-green-700 text-gray-100 transition rounded"
      type="submit"
    >
      Save
    </button>
  </div>
</form>
