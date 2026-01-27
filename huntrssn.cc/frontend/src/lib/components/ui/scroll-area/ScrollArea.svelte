<script lang="ts">
  let { class: className = '', children, ...restProps }: any = $props();
</script>

<div class="overflow-auto {className}" {...restProps}>
  {@render children?.()}
</div>
