import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FadeIn from '../design/motion/FadeIn';
import Stagger from '../design/motion/Stagger';

describe('motion primitives', () => {
  test('FadeIn renders its children', () => {
    render(<FadeIn><span>visible</span></FadeIn>);
    expect(screen.getByText('visible')).toBeTruthy();
  });

  test('Stagger renders all children', () => {
    render(<Stagger><div>a</div><div>b</div><div>c</div></Stagger>);
    expect(screen.getByText('a')).toBeTruthy();
    expect(screen.getByText('c')).toBeTruthy();
  });
});
