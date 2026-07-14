// 版本比较保持为纯 JavaScript，不依赖 React 或 Tauri。
// 这样它既能在界面中使用，也能直接通过 Node.js 做单元测试。
function parseVersion(version) {
  const text = String(version || "")
    .trim()
    .replace(/^v/i, "")
    .split("+", 1)[0];
  const match = text.match(/^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?$/);
  if (!match) {
    throw new Error(`无法识别版本号：${version || "空值"}`);
  }

  return {
    numbers: [Number(match[1]), Number(match[2] || 0), Number(match[3] || 0)],
    prerelease: match[4] ? match[4].split(".") : [],
  };
}

function comparePrerelease(left, right) {
  if (left.length === 0 && right.length === 0) {
    return 0;
  }
  if (left.length === 0) {
    return 1;
  }
  if (right.length === 0) {
    return -1;
  }

  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = left[index];
    const rightPart = right[index];
    if (leftPart === undefined) {
      return -1;
    }
    if (rightPart === undefined) {
      return 1;
    }
    if (leftPart === rightPart) {
      continue;
    }

    const leftIsNumber = /^\d+$/.test(leftPart);
    const rightIsNumber = /^\d+$/.test(rightPart);
    if (leftIsNumber && rightIsNumber) {
      return Number(leftPart) < Number(rightPart) ? -1 : 1;
    }
    if (leftIsNumber !== rightIsNumber) {
      return leftIsNumber ? -1 : 1;
    }
    return leftPart.localeCompare(rightPart, "en") < 0 ? -1 : 1;
  }
  return 0;
}

// 返回值小于 0 表示 left 较旧，等于 0 表示相同，大于 0 表示 left 较新。
export function compareVersions(left, right) {
  const parsedLeft = parseVersion(left);
  const parsedRight = parseVersion(right);

  for (let index = 0; index < parsedLeft.numbers.length; index += 1) {
    if (parsedLeft.numbers[index] === parsedRight.numbers[index]) {
      continue;
    }
    return parsedLeft.numbers[index] < parsedRight.numbers[index] ? -1 : 1;
  }
  return comparePrerelease(parsedLeft.prerelease, parsedRight.prerelease);
}
