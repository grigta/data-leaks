<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  onMount(() => {
    const token = localStorage.getItem('worker_token');
    goto(token ? '/dashboard' : '/login');
  });
</script>
