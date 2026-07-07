export function dragScrollY(node) {
	let isDown = false;
	let startY;
	let scrollTop;
	let dragged = false;

	function mousedown(e) {
		if (e.button !== 0) return; // Only left mouse button
		isDown = true;
		dragged = false;
		startY = e.pageY;
		scrollTop = node.scrollTop;
		node.style.cursor = 'grabbing';
	}

	function mouseup(e) {
		if (isDown) {
			isDown = false;
			node.style.cursor = '';
			// We delay resetting `dragged` to allow the click event to fire and be intercepted
			setTimeout(() => {
				dragged = false;
			}, 0);
		}
	}

	function mousemove(e) {
		if (!isDown) return;
		
		const y = e.pageY;
		const walk = (y - startY); // 1:1 movement
		
		// Threshold to start treating it as a drag
		if (Math.abs(walk) > 5) {
			dragged = true;
		}

		if (dragged) {
			e.preventDefault(); // prevent text selection
			node.scrollTop = scrollTop - walk;
		}
	}

	function click(e) {
		if (dragged) {
			e.preventDefault();
			e.stopPropagation();
		}
	}

	function dragstart(e) {
		e.preventDefault();
	}

	node.addEventListener('mousedown', mousedown);
	window.addEventListener('mouseup', mouseup);
	window.addEventListener('mousemove', mousemove, { passive: false });
	node.addEventListener('click', click, { capture: true });
	node.addEventListener('dragstart', dragstart);

	return {
		destroy() {
			node.removeEventListener('mousedown', mousedown);
			window.removeEventListener('mouseup', mouseup);
			window.removeEventListener('mousemove', mousemove);
			node.removeEventListener('click', click, { capture: true });
			node.removeEventListener('dragstart', dragstart);
		}
	};
}
