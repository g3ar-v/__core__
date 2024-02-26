<script lang="ts">
  import { systemSpeaking } from "$lib/stores";
  import toast from "svelte-french-toast";
  // import Suggestions from "./MessageInput/Suggestions.svelte";

  export let submitPrompt: Function;
  export let stopSpeaking: Function;
  export let microphoneHandler: Function;
  export let listenHandler: Function;
  export let stopListening: Function;

  // export let suggestionPrompts = [];
  export let autoScroll = true;

  export let speechRecognitionListening = false;
  export let isMicrophoneMuted = false;

  export let prompt = "";
  export let messages = [];
</script>

<div class="fixed bottom-0 w-full bg-white dark:bg-gray-800">
  <div class=" absolute right-0 left-0 bottom-0 mb-20">
    <div class="max-w-3xl px-2.5 pt-2.5 -mb-0.5 mx-auto inset-x-0">
      <!-- {#if messages.length == 0 && suggestionPrompts.length !== 0} -->
      <!--   <Suggestions {suggestionPrompts} {submitPrompt} /> -->
      <!-- {/if} -->

      {#if autoScroll === false && messages.length > 0}
        <div class=" flex justify-center mb-4">
          <button
            class=" bg-white border border-gray-100 dark:border-none dark:bg-white/20 p-1.5 rounded-full"
            on:click={() => {
              autoScroll = true;
              window.scrollTo({
                top: document.body.scrollHeight,
                behavior: "smooth",
              });
            }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              class="w-5 h-5"
            >
              <path
                fill-rule="evenodd"
                d="M10 3a.75.75 0 01.75.75v10.638l3.96-4.158a.75.75 0 111.08 1.04l-5.25 5.5a.75.75 0 01-1.08 0l-5.25-5.5a.75.75 0 111.08-1.04l3.96 4.158V3.75A.75.75 0 0110 3z"
                clip-rule="evenodd"
              />
            </svg>
          </button>
        </div>
      {/if}
    </div>
  </div>
  <div>
    <div class="max-w-3xl px-2.5 -mb-0.5 mx-auto inset-x-0">
      <div class="bg-gradient-to-t from-white dark:from-gray-800 from-40% pb-2">
        <form
          class=" flex flex-col relative w-full rounded-xl border dark:border-gray-600 bg-white dark:bg-gray-800 dark:text-gray-100"
          on:submit|preventDefault={() => {
            if ($systemSpeaking) {
              stopSpeaking();
            } else if (speechRecognitionListening) {
              console.log("speech is listening");
              stopListening();
            } else {
              submitPrompt(prompt);
            }
          }}
        >
          {#if speechRecognitionListening == true}
            <div class="flex justify-between">
              <div class="flex ml-5 align-items content-center;">
                <svg
                  class=" w-10 h-10 translate-y-[0.5px] fill-gray-50"
                  viewBox="0 0 24 24"
                  xmlns="http://www.w3.org/2000/svg"
                  ><style>
                    .spinner_qM83 {
                      animation: spinner_8HQG 1.05s infinite;
                    }
                    .spinner_oXPr {
                      animation-delay: 0.1s;
                    }
                    .spinner_ZTLf {
                      animation-delay: 0.2s;
                    }
                    @keyframes spinner_8HQG {
                      0%,
                      57.14% {
                        animation-timing-function: cubic-bezier(
                          0.33,
                          0.66,
                          0.66,
                          1
                        );
                        transform: translate(0);
                      }
                      28.57% {
                        animation-timing-function: cubic-bezier(
                          0.33,
                          0,
                          0.66,
                          0.33
                        );
                        transform: translateY(-6px);
                      }
                      100% {
                        transform: translate(0);
                      }
                    }
                  </style><circle
                    class="spinner_qM83"
                    cx="4"
                    cy="12"
                    r="2.5"
                  /><circle
                    class="spinner_qM83 spinner_oXPr"
                    cx="12"
                    cy="12"
                    r="2.5"
                  /><circle
                    class="spinner_qM83 spinner_ZTLf"
                    cx="20"
                    cy="12"
                    r="2.5"
                  /></svg
                >
              </div>
              <div class="self-end mb-1 flex space-x-1.5 mr-2">
                <button
                  class="bg-white hover:bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-white dark:hover:bg-gray-800 transition rounded-lg p-1.5"
                  on:click={stopListening()}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    class="w-5 h-5"
                  >
                    <path
                      fill-rule="evenodd"
                      d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm6-2.438c0-.724.588-1.312 1.313-1.312h4.874c.725 0 1.313.588 1.313 1.313v4.874c0 .725-.588 1.313-1.313 1.313H9.564a1.312 1.312 0 01-1.313-1.313V9.564z"
                      clip-rule="evenodd"
                    />
                  </svg>
                </button>
              </div>
            </div>
          {:else}
            <div class=" flex">
              <textarea
                id="chat-textarea"
                class="font-sans dark:bg-gray-800 dark:text-gray-300 outline-none w-full py-3 px-2 pl-4 rounded-xl resize-none"
                placeholder="Send a message"
                bind:value={prompt}
                on:keypress={(e) => {
                  if (e.keyCode == 13 && !e.shiftKey) {
                    e.preventDefault();
                  }
                  if (prompt !== "" && e.keyCode == 13 && !e.shiftKey) {
                    submitPrompt(prompt);
                  }
                }}
                rows="1"
                on:input={(e) => {
                  e.target.style.height = "";
                  e.target.style.height =
                    Math.min(e.target.scrollHeight, 200) + "px";
                }}
              />

              <div class="self-end mb-2 flex space-x-1.5 mr-2">
                {#if $systemSpeaking === false}
                  <!-- listen button -->
                  <button
                    class="bg-white hover:bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700 transition rounded-lg p-1.5"
                    type="button"
                    on:click={listenHandler()}
                  >
                    <span
                      class="before:content-[attr(data-tip)]
                          before:absolute
                          before:px-3 before:py-2
                          before:right-16 before:bottom-16
                          before:w-max before:max-w-xs
                          before:translate-x-2.5 before:translate-y-2.5
                          before:bg-gray-900 before:text-white
                          before:rounded-md before:opacity-0
                          before:transition-all

                          hover:before:opacity-100
                    "
                      data-tip="activate listen"
                    >
                      <svg
                        height="16px"
                        width="16px"
                        xmlns="http://www.w3.org/2000/svg"
                        class="fill-red-950"
                        ><path
                          d="m8 1a7 7 0 0 0 -7 7 7 7 0 0 0 7 7 7 7 0 0 0 7-7 7 7 0 0 0 -7-7zm0 1a6 6 0 0 1 6 6 6 6 0 0 1 -6 6 6 6 0 0 1 -6-6 6 6 0 0 1 6-6zm0 1a5 5 0 0 0 -5 5 5 5 0 0 0 5 5 5 5 0 0 0 5-5 5 5 0 0 0 -5-5z"
                        /></svg
                      >
                    </span>
                  </button>
                  <button
                    class="bg-white hover:bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700 transition rounded-lg p-1.5"
                    type="button"
                    on:click={() => {
                      const mutedFlag = microphoneHandler();
                      mutedFlag.then((muteMicrophoneFlag) => {
                        isMicrophoneMuted = muteMicrophoneFlag;
                      });
                    }}
                  >
                    <!-- mute/unmute button -->
                    {#if isMicrophoneMuted}
                      <span
                        class="before:content-[attr(data-tip)]
                          before:absolute
                          before:px-3 before:py-2
                          before:right-16 before:bottom-16
                          before:w-max before:max-w-xs
                          before:translate-x-2.5 before:translate-y-2.5
                          before:bg-gray-900 before:text-white
                          before:rounded-md before:opacity-0
                          before:transition-all

                          hover:before:opacity-100
                    "
                        data-tip="unmute mic"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          class="fill-red-950 w-5 h-5 translate-y-[0.5px]"
                        >
                          <path d="M7 4a3 3 0 016 0v6a3 3 0 11-6 0V4z" />
                          <path
                            d="M5.5 9.643a.75.75 0 00-1.5 0V10c0 3.06 2.29 5.585 5.25 5.954V17.5h-1.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-1.5v-1.546A6.001 6.001 0 0016 10v-.357a.75.75 0 00-1.5 0V10a4.5 4.5 0 01-9 0v-.357z"
                          />
                          <!-- Diagonal line to indicate the microphone is muted -->
                          <line
                            x1="4"
                            y1="4"
                            x2="16"
                            y2="16"
                            class="stroke-red-950 stroke-2"
                          />
                        </svg>
                      </span>
                    {:else}
                      <span
                        class="before:content-[attr(data-tip)]
                          before:absolute
                          before:px-3 before:py-2
                          before:right-16 before:bottom-16
                          before:w-max before:max-w-xs
                          before:translate-x-2.5 before:translate-y-2.5
                          before:bg-gray-900 before:text-white
                          before:rounded-md before:opacity-0
                          before:transition-all

                          hover:before:opacity-100
                    "
                        data-tip="mute mic"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          class="fill-gray-400 w-5 h-5 translate-y-[0.5px]"
                        >
                          <path d="M7 4a3 3 0 016 0v6a3 3 0 11-6 0V4z" />
                          <path
                            d="M5.5 9.643a.75.75 0 00-1.5 0V10c0 3.06 2.29 5.585 5.25 5.954V17.5h-1.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-1.5v-1.546A6.001 6.001 0 0016 10v-.357a.75.75 0 00-1.5 0V10a4.5 4.5 0 01-9 0v-.357z"
                          />
                        </svg>
                      </span>
                    {/if}
                  </button>

                  <!-- submit button -->
                  <button
                    class="{prompt !== ''
                      ? 'bg-black text-white hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-200 '
                      : 'text-white bg-gray-100 dark:text-gray-800 dark:bg-gray-600 disabled'} transition rounded-lg p-1 mr-0.5 w-7 h-7 self-center"
                    type="submit"
                    disabled={prompt === ""}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      class="w-5 h-5"
                    >
                      <path
                        fill-rule="evenodd"
                        d="M10 17a.75.75 0 01-.75-.75V5.612L5.29 9.77a.75.75 0 01-1.08-1.04l5.25-5.5a.75.75 0 011.08 0l5.25 5.5a.75.75 0 11-1.08 1.04l-3.96-4.158V16.25A.75.75 0 0110 17z"
                        clip-rule="evenodd"
                      />
                    </svg>
                  </button>
                {:else}
                  <!-- stop system speech button -->
                  <button
                    class="bg-white hover:bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-white dark:hover:bg-gray-800 transition rounded-lg p-1.5"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      class="w-5 h-5"
                    >
                      <path
                        fill-rule="evenodd"
                        d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm6-2.438c0-.724.588-1.312 1.313-1.312h4.874c.725 0 1.313.588 1.313 1.313v4.874c0 .725-.588 1.313-1.313 1.313H9.564a1.312 1.312 0 01-1.313-1.313V9.564z"
                        clip-rule="evenodd"
                      />
                    </svg>
                  </button>
                {/if}
              </div>
            </div>
          {/if}
        </form>

        <div class="mt-1.5 text-xs text-gray-500 text-center">
          Vasco can make mistakes. Verify important information.
        </div>
      </div>
    </div>
  </div>
</div>
