import { Collapsible as CollapsiblePrimitive } from "bits-ui";

const Root = CollapsiblePrimitive.Root;
const Trigger = CollapsiblePrimitive.Trigger;
const Content = CollapsiblePrimitive.Content;

export {
	Root,
	Content,
	Trigger,
	//
	Root as Collapsible,
	Content as CollapsibleContent,
	Trigger as CollapsibleTrigger,
};

export * as Tabs from "./tabs";
export * as Textarea from "./textarea";
